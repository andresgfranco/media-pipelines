#!/bin/bash
# Complete deployment script for Media Pipelines to AWS
# This script creates all necessary AWS resources and deploys the pipelines

set -e

echo "🚀 Media Pipelines - Complete AWS Deployment"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
check_prerequisite() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}❌ $1 not found. Please install it first.${NC}"
        exit 1
    fi
}

echo "🔍 Checking prerequisites..."
check_prerequisite "aws"
check_prerequisite "zip"
check_prerequisite "python3"
echo -e "${GREEN}✅ All prerequisites met${NC}"
echo ""

# Configuration
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
TIMESTAMP=$(date +%s)

if [ -z "$ACCOUNT_ID" ]; then
    echo -e "${RED}❌ AWS credentials not configured. Run 'aws configure' first.${NC}"
    exit 1
fi

# Resource names
PROJECT_PREFIX="media-pipelines"
AUDIO_BUCKET="${PROJECT_PREFIX}-audio-${TIMESTAMP}"
VIDEO_BUCKET="${PROJECT_PREFIX}-video-${TIMESTAMP}"
METADATA_TABLE="${PROJECT_PREFIX}-metadata"
LAMBDA_ROLE_NAME="${PROJECT_PREFIX}-lambda-execution-role"
STEPFUNCTIONS_ROLE_NAME="${PROJECT_PREFIX}-stepfunctions-execution-role"
SNS_TOPIC_NAME="${PROJECT_PREFIX}-notifications"

echo "📍 Configuration:"
echo "   Region: $REGION"
echo "   Account ID: $ACCOUNT_ID"
echo "   Audio Bucket: $AUDIO_BUCKET"
echo "   Video Bucket: $VIDEO_BUCKET"
echo "   Metadata Table: $METADATA_TABLE"
echo ""

# Step 1: Create S3 buckets
echo "📦 Step 1: Creating S3 buckets..."
aws s3 mb "s3://${AUDIO_BUCKET}" --region "$REGION" 2>/dev/null || echo -e "${YELLOW}⚠️  Audio bucket may already exist${NC}"
aws s3 mb "s3://${VIDEO_BUCKET}" --region "$REGION" 2>/dev/null || echo -e "${YELLOW}⚠️  Video bucket may already exist${NC}"
echo -e "${GREEN}✅ S3 buckets created${NC}"
echo ""

# Step 2: Create DynamoDB table
echo "🗄️  Step 2: Creating DynamoDB table..."
aws dynamodb create-table \
  --table-name "$METADATA_TABLE" \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || echo -e "${YELLOW}⚠️  Table may already exist${NC}"

# Wait for table to be active
echo "   Waiting for table to be active..."
aws dynamodb wait table-exists --table-name "$METADATA_TABLE" --region "$REGION" 2>/dev/null || true
echo -e "${GREEN}✅ DynamoDB table ready${NC}"
echo ""

# Step 3: Create IAM roles
echo "🔐 Step 3: Creating IAM roles..."

# Lambda execution role
LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" --region "$REGION" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Lambda role already exists${NC}"
else
    echo "   Creating Lambda execution role..."
    aws iam create-role \
      --role-name "$LAMBDA_ROLE_NAME" \
      --assume-role-policy-document file://scripts/lambda-trust-policy.json \
      --region "$REGION" > /dev/null

    # Update policy with actual bucket names
    sed "s|media-pipelines-audio-\*|${AUDIO_BUCKET}/*|g; s|media-pipelines-video-\*|${VIDEO_BUCKET}/*|g; s|media-pipelines-metadata|${METADATA_TABLE}|g; s|media-pipelines-notifications|${SNS_TOPIC_NAME}|g" \
      scripts/lambda-policy.json > /tmp/lambda-policy-updated.json

    aws iam put-role-policy \
      --role-name "$LAMBDA_ROLE_NAME" \
      --policy-name "${LAMBDA_ROLE_NAME}-policy" \
      --policy-document file:///tmp/lambda-policy-updated.json \
      --region "$REGION" > /dev/null

    echo -e "${GREEN}✅ Lambda role created${NC}"
fi

# Step Functions execution role
STEPFUNCTIONS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${STEPFUNCTIONS_ROLE_NAME}"
if aws iam get-role --role-name "$STEPFUNCTIONS_ROLE_NAME" --region "$REGION" &>/dev/null; then
    echo -e "${YELLOW}⚠️  Step Functions role already exists${NC}"
else
    echo "   Creating Step Functions execution role..."
    aws iam create-role \
      --role-name "$STEPFUNCTIONS_ROLE_NAME" \
      --assume-role-policy-document file://scripts/stepfunctions-trust-policy.json \
      --region "$REGION" > /dev/null

    # Update policy with actual account ID
    sed "s|ACCOUNT_ID|${ACCOUNT_ID}|g" scripts/stepfunctions-policy.json > /tmp/stepfunctions-policy-updated.json

    aws iam put-role-policy \
      --role-name "$STEPFUNCTIONS_ROLE_NAME" \
      --policy-name "${STEPFUNCTIONS_ROLE_NAME}-policy" \
      --policy-document file:///tmp/stepfunctions-policy-updated.json \
      --region "$REGION" > /dev/null

    echo -e "${GREEN}✅ Step Functions role created${NC}"
fi
echo ""

# Step 4: Create SNS topic (optional)
echo "📢 Step 4: Creating SNS topic..."
SNS_TOPIC_ARN=$(aws sns create-topic \
  --name "$SNS_TOPIC_NAME" \
  --region "$REGION" \
  --query 'TopicArn' --output text 2>/dev/null || echo "")
if [ -n "$SNS_TOPIC_ARN" ]; then
  echo -e "${GREEN}✅ SNS topic created: $SNS_TOPIC_ARN${NC}"
else
  echo -e "${YELLOW}⚠️  SNS topic creation skipped${NC}"
fi
echo ""

# Step 5: Package Lambda functions
echo "📦 Step 5: Packaging Lambda functions..."
DEPLOY_DIR="deploy-lambda-$(date +%s)"
mkdir -p "$DEPLOY_DIR"

# Install dependencies
echo "   Installing dependencies..."
pip install -q -r <(python3 -c "
import tomli
with open('pyproject.toml', 'rb') as f:
    data = tomli.load(f)
    deps = data.get('project', {}).get('dependencies', [])
    for dep in deps:
        print(dep)
") -t "$DEPLOY_DIR" 2>/dev/null || pip install -q boto3 requests -t "$DEPLOY_DIR"

# Install audio dependencies
pip install -q pydub librosa -t "$DEPLOY_DIR" 2>/dev/null || echo "   Warning: Some audio dependencies may not be available"

# Copy source code
echo "   Copying source code..."
cp -r shared "$DEPLOY_DIR/"
cp -r audio_pipeline "$DEPLOY_DIR/"
cp -r video_pipeline "$DEPLOY_DIR/"
cp -r infrastructure "$DEPLOY_DIR/"

# Create deployment packages for each Lambda
LAMBDA_HANDLERS=(
    "audio_ingest:infrastructure.handlers.audio_ingest.handler"
    "audio_analyze:infrastructure.handlers.audio_analyze.handler"
    "index_audio:infrastructure.handlers.index_audio.handler"
    "video_ingest:infrastructure.handlers.video_ingest.handler"
    "video_rekognition_start:infrastructure.handlers.video_rekognition_start.handler"
    "video_rekognition_check:infrastructure.handlers.video_rekognition_check.handler"
    "video_rekognition_finalize:infrastructure.handlers.video_rekognition_finalize.handler"
    "index_video:infrastructure.handlers.index_video.handler"
)

echo "   Creating Lambda packages..."
for handler_spec in "${LAMBDA_HANDLERS[@]}"; do
    IFS=':' read -r function_name handler_path <<< "$handler_spec"
    zip_file="lambda-${function_name}.zip"

    cd "$DEPLOY_DIR"
    zip -q -r "../${zip_file}" . -x "*.pyc" "__pycache__/*" "*.dist-info/*"
    cd ..

    echo "      ✅ Created $zip_file"
done

echo -e "${GREEN}✅ Lambda packages created${NC}"
echo ""

# Step 6: Deploy Lambda functions
echo "🚀 Step 6: Deploying Lambda functions..."

# Base environment variables for all Lambda functions
ENV_VARS_BASE="{
  \"MEDIA_PIPELINES_AUDIO_BUCKET\": \"${AUDIO_BUCKET}\",
  \"MEDIA_PIPELINES_VIDEO_BUCKET\": \"${VIDEO_BUCKET}\",
  \"MEDIA_PIPELINES_METADATA_TABLE\": \"${METADATA_TABLE}\",
  \"MEDIA_PIPELINES_AWS_REGION\": \"${REGION}\"
}"

# Environment variables for video_ingest (includes Pixabay API key if available)
ENV_VARS_VIDEO_INGEST="${ENV_VARS_BASE}"
if [ -n "${PIXABAY_API_KEY:-}" ]; then
    ENV_VARS_VIDEO_INGEST="${ENV_VARS_BASE},
  \"MEDIA_PIPELINES_PIXABAY_API_KEY\": \"${PIXABAY_API_KEY}\""
    echo "   ✅ Pixabay API key will be configured in video_ingest Lambda function"
else
    echo "   ⚠️  No PIXABAY_API_KEY found - video pipeline will only use Wikimedia Commons"
fi
ENV_VARS_VIDEO_INGEST="${ENV_VARS_VIDEO_INGEST}
}"

LAMBDA_FUNCTIONS=()
for handler_spec in "${LAMBDA_HANDLERS[@]}"; do
    IFS=':' read -r function_name handler_path <<< "$handler_spec"
    function_name_full="${PROJECT_PREFIX}-${function_name}"
    zip_file="lambda-${function_name}.zip"

    echo "   Deploying $function_name_full..."

    # Use video_ingest-specific env vars only for video_ingest function
    if [ "$function_name" = "video_ingest" ]; then
        ENV_VARS_TO_USE="$ENV_VARS_VIDEO_INGEST"
    else
        ENV_VARS_TO_USE="${ENV_VARS_BASE}
}"
    fi

    # Check if function exists
    if aws lambda get-function --function-name "$function_name_full" --region "$REGION" &>/dev/null; then
        # Update existing function
        aws lambda update-function-code \
          --function-name "$function_name_full" \
          --zip-file "fileb://${zip_file}" \
          --region "$REGION" > /dev/null

        aws lambda update-function-configuration \
          --function-name "$function_name_full" \
          --timeout 300 \
          --memory-size 512 \
          --environment "Variables=${ENV_VARS_TO_USE}" \
          --region "$REGION" > /dev/null

        echo "      ✅ Updated $function_name_full"
    else
        # Create new function
        aws lambda create-function \
          --function-name "$function_name_full" \
          --runtime python3.11 \
          --role "$LAMBDA_ROLE_ARN" \
          --handler "$handler_path" \
          --zip-file "fileb://${zip_file}" \
          --timeout 300 \
          --memory-size 512 \
          --environment "Variables=${ENV_VARS_TO_USE}" \
          --region "$REGION" > /dev/null

        echo "      ✅ Created $function_name_full"
    fi

    # Get function ARN
    FUNCTION_ARN=$(aws lambda get-function --function-name "$function_name_full" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
    LAMBDA_FUNCTIONS+=("$FUNCTION_ARN")
done

echo -e "${GREEN}✅ All Lambda functions deployed${NC}"
echo ""

# Step 7: Deploy Step Functions
echo "🔄 Step 7: Deploying Step Functions state machines..."

# Audio State Machine
echo "   Deploying Audio Pipeline State Machine..."
AUDIO_INGEST_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-audio_ingest" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
AUDIO_ANALYZE_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-audio_analyze" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
AUDIO_INDEX_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-index_audio" --region "$REGION" --query 'Configuration.FunctionArn' --output text)

sed "s|\${IngestAudioFunctionArn}|${AUDIO_INGEST_ARN}|g; s|\${AnalyzeAudioFunctionArn}|${AUDIO_ANALYZE_ARN}|g; s|\${IndexAudioFunctionArn}|${AUDIO_INDEX_ARN}|g" \
  infrastructure/audio_state_machine.asl.json > /tmp/audio_sm.json

AUDIO_SM_NAME="${PROJECT_PREFIX}-audio-pipeline"
AUDIO_SM_ARN_POTENTIAL="arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:${AUDIO_SM_NAME}"
if aws stepfunctions describe-state-machine --state-machine-arn "$AUDIO_SM_ARN_POTENTIAL" --region "$REGION" &>/dev/null; then
    AUDIO_SM_ARN=$(aws stepfunctions update-state-machine \
      --state-machine-arn "$AUDIO_SM_ARN_POTENTIAL" \
      --definition file:///tmp/audio_sm.json \
      --region "$REGION" \
      --query 'stateMachineArn' --output text)
    echo "      ✅ Updated Audio Pipeline State Machine"
else
    AUDIO_SM_ARN=$(aws stepfunctions create-state-machine \
      --name "$AUDIO_SM_NAME" \
      --definition file:///tmp/audio_sm.json \
      --role-arn "$STEPFUNCTIONS_ROLE_ARN" \
      --region "$REGION" \
      --query 'stateMachineArn' --output text)
    echo "      ✅ Created Audio Pipeline State Machine"
fi

# Video State Machine
echo "   Deploying Video Pipeline State Machine..."
VIDEO_INGEST_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-video_ingest" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
VIDEO_REK_START_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-video_rekognition_start" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
VIDEO_REK_CHECK_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-video_rekognition_check" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
VIDEO_REK_FINALIZE_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-video_rekognition_finalize" --region "$REGION" --query 'Configuration.FunctionArn' --output text)
VIDEO_INDEX_ARN=$(aws lambda get-function --function-name "${PROJECT_PREFIX}-index_video" --region "$REGION" --query 'Configuration.FunctionArn' --output text)

sed "s|\${IngestVideoFunctionArn}|${VIDEO_INGEST_ARN}|g; s|\${StartRekognitionFunctionArn}|${VIDEO_REK_START_ARN}|g; s|\${CheckRekognitionStatusFunctionArn}|${VIDEO_REK_CHECK_ARN}|g; s|\${FinalizeRekognitionFunctionArn}|${VIDEO_REK_FINALIZE_ARN}|g; s|\${IndexVideoFunctionArn}|${VIDEO_INDEX_ARN}|g" \
  infrastructure/video_state_machine.asl.json > /tmp/video_sm.json

VIDEO_SM_NAME="${PROJECT_PREFIX}-video-pipeline"
VIDEO_SM_ARN_POTENTIAL="arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:${VIDEO_SM_NAME}"
if aws stepfunctions describe-state-machine --state-machine-arn "$VIDEO_SM_ARN_POTENTIAL" --region "$REGION" &>/dev/null; then
    VIDEO_SM_ARN=$(aws stepfunctions update-state-machine \
      --state-machine-arn "$VIDEO_SM_ARN_POTENTIAL" \
      --definition file:///tmp/video_sm.json \
      --region "$REGION" \
      --query 'stateMachineArn' --output text)
    echo "      ✅ Updated Video Pipeline State Machine"
else
    VIDEO_SM_ARN=$(aws stepfunctions create-state-machine \
      --name "$VIDEO_SM_NAME" \
      --definition file:///tmp/video_sm.json \
      --role-arn "$STEPFUNCTIONS_ROLE_ARN" \
      --region "$REGION" \
      --query 'stateMachineArn' --output text)
    echo "      ✅ Created Video Pipeline State Machine"
fi

echo -e "${GREEN}✅ State machines deployed${NC}"
echo ""

# Save configuration to file
CONFIG_FILE=".aws-deployment-config"
cat > "$CONFIG_FILE" <<EOF
# AWS Deployment Configuration
# Generated on $(date)
export MEDIA_PIPELINES_AUDIO_BUCKET=$AUDIO_BUCKET
export MEDIA_PIPELINES_VIDEO_BUCKET=$VIDEO_BUCKET
export MEDIA_PIPELINES_METADATA_TABLE=$METADATA_TABLE
export MEDIA_PIPELINES_AWS_REGION=$REGION
export MEDIA_PIPELINES_AUDIO_STATE_MACHINE_ARN=$AUDIO_SM_ARN
export MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN=$VIDEO_SM_ARN
EOF

# Cleanup
rm -rf "$DEPLOY_DIR"
rm -f lambda-*.zip
rm -f /tmp/*-policy-updated.json /tmp/*_sm.json

# Summary
echo "=============================================="
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo "=============================================="
echo ""
echo "📋 Configuration Summary:"
echo "   Audio Bucket: $AUDIO_BUCKET"
echo "   Video Bucket: $VIDEO_BUCKET"
echo "   Metadata Table: $METADATA_TABLE"
echo "   Region: $REGION"
echo ""
echo "🔗 State Machine ARNs:"
echo "   Audio: $AUDIO_SM_ARN"
echo "   Video: $VIDEO_SM_ARN"
echo ""
echo "💾 Configuration saved to: $CONFIG_FILE"
echo "   Load it with: source $CONFIG_FILE"
echo ""
echo "💾 Environment variables:"
echo "export MEDIA_PIPELINES_AUDIO_BUCKET=$AUDIO_BUCKET"
echo "export MEDIA_PIPELINES_VIDEO_BUCKET=$VIDEO_BUCKET"
echo "export MEDIA_PIPELINES_METADATA_TABLE=$METADATA_TABLE"
echo "export MEDIA_PIPELINES_AWS_REGION=$REGION"
echo "export MEDIA_PIPELINES_AUDIO_STATE_MACHINE_ARN=$AUDIO_SM_ARN"
echo "export MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN=$VIDEO_SM_ARN"
echo ""
echo "🧪 Test the pipelines:"
echo "   source $CONFIG_FILE"
echo "   python scripts/test_aws_deployment.py"
echo ""
echo "   Or manually trigger:"
echo "   python infrastructure/schedule_trigger.py audio nature 1"
echo "   python infrastructure/schedule_trigger.py video nature 1"
echo ""
