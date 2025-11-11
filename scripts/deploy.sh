#!/bin/bash
# Quick deployment script for Media Pipelines
# This is a simplified version - see docs/deployment.md for full details

set -e

echo "🚀 Media Pipelines Deployment Script"
echo "======================================"

# Check prerequisites
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first."
    exit 1
fi

if ! command -v zip &> /dev/null; then
    echo "❌ zip not found. Please install it first."
    exit 1
fi

# Configuration
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TIMESTAMP=$(date +%s)
AUDIO_BUCKET="media-pipelines-audio-${TIMESTAMP}"
VIDEO_BUCKET="media-pipelines-video-${TIMESTAMP}"
METADATA_TABLE="media-pipelines-metadata"

echo "📍 Region: $REGION"
echo "🔢 Account ID: $ACCOUNT_ID"
echo "📦 Audio Bucket: $AUDIO_BUCKET"
echo "📦 Video Bucket: $VIDEO_BUCKET"
echo ""

# Step 1: Create S3 buckets
echo "📦 Creating S3 buckets..."
aws s3 mb "s3://${AUDIO_BUCKET}" --region "$REGION" || true
aws s3 mb "s3://${VIDEO_BUCKET}" --region "$REGION" || true
echo "✅ S3 buckets created"

# Step 2: Create DynamoDB table
echo "🗄️  Creating DynamoDB table..."
aws dynamodb create-table \
  --table-name "$METADATA_TABLE" \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || echo "⚠️  Table may already exist"
echo "✅ DynamoDB table ready"

# Step 3: Create SNS topic (optional)
echo "📢 Creating SNS topic..."
SNS_TOPIC_ARN=$(aws sns create-topic \
  --name media-pipelines-notifications \
  --region "$REGION" \
  --query 'TopicArn' --output text 2>/dev/null || echo "")
if [ -n "$SNS_TOPIC_ARN" ]; then
  echo "✅ SNS topic created: $SNS_TOPIC_ARN"
else
  echo "⚠️  SNS topic creation skipped or already exists"
fi

echo ""
echo "✅ Basic infrastructure created!"
echo ""
echo "📝 Next steps:"
echo "1. Create IAM roles for Lambda and Step Functions (see docs/deployment.md)"
echo "2. Package and deploy Lambda functions"
echo "3. Deploy Step Functions state machines"
echo "4. Configure EventBridge rules"
echo "5. Deploy Streamlit dashboard (see docs/streamlit-deploy.md)"
echo ""
echo "📚 Full deployment guide: docs/deployment.md"
echo ""
echo "💾 Save these values for configuration:"
echo "export MEDIA_PIPELINES_AUDIO_BUCKET=$AUDIO_BUCKET"
echo "export MEDIA_PIPELINES_VIDEO_BUCKET=$VIDEO_BUCKET"
echo "export MEDIA_PIPELINES_METADATA_TABLE=$METADATA_TABLE"
echo "export MEDIA_PIPELINES_AWS_REGION=$REGION"
