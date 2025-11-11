#!/bin/bash

# Script to clean up audio pipeline resources from AWS
# This removes Lambda functions, Step Functions state machines, EventBridge rules, and S3 buckets
# related to the audio pipeline that we've removed from the codebase.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_PREFIX="media-pipelines"
REGION="${AWS_REGION:-us-east-1}"

echo "🧹 Cleaning up audio pipeline resources from AWS..."
echo "   Region: $REGION"
echo "   Project Prefix: $PROJECT_PREFIX"
echo ""

# Step 1: Remove EventBridge rules
echo "📅 Step 1: Removing EventBridge rules..."
AUDIO_RULE_NAME="${PROJECT_PREFIX}-audio-weekly"
if aws events describe-rule --name "$AUDIO_RULE_NAME" --region "$REGION" &>/dev/null; then
    # Remove targets first
    aws events remove-targets \
        --rule "$AUDIO_RULE_NAME" \
        --ids "1" \
        --region "$REGION" 2>/dev/null || true

    # Delete the rule
    aws events delete-rule \
        --name "$AUDIO_RULE_NAME" \
        --region "$REGION" 2>/dev/null

    echo "   ✅ Removed EventBridge rule: $AUDIO_RULE_NAME"
else
    echo "   ℹ️  EventBridge rule not found: $AUDIO_RULE_NAME"
fi
echo ""

# Step 2: Remove Step Functions state machine
echo "🔄 Step 2: Removing Step Functions state machine..."
AUDIO_SM_NAME="${PROJECT_PREFIX}-audio-pipeline"
AUDIO_SM_ARN_POTENTIAL="arn:aws:states:${REGION}:$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo 'ACCOUNT'):stateMachine:${AUDIO_SM_NAME}"

if aws stepfunctions describe-state-machine --state-machine-arn "$AUDIO_SM_ARN_POTENTIAL" --region "$REGION" &>/dev/null; then
    # First, stop all running executions
    echo "   Stopping running executions..."
    EXECUTIONS=$(aws stepfunctions list-executions \
        --state-machine-arn "$AUDIO_SM_ARN_POTENTIAL" \
        --status-filter RUNNING \
        --region "$REGION" \
        --query 'executions[].executionArn' \
        --output text 2>/dev/null || echo "")

    if [ -n "$EXECUTIONS" ]; then
        for exec_arn in $EXECUTIONS; do
            aws stepfunctions stop-execution \
                --execution-arn "$exec_arn" \
                --region "$REGION" 2>/dev/null || true
        done
        echo "   ✅ Stopped running executions"
    fi

    # Delete the state machine
    aws stepfunctions delete-state-machine \
        --state-machine-arn "$AUDIO_SM_ARN_POTENTIAL" \
        --region "$REGION" 2>/dev/null

    echo "   ✅ Removed Step Functions state machine: $AUDIO_SM_NAME"
else
    echo "   ℹ️  Step Functions state machine not found: $AUDIO_SM_NAME"
fi
echo ""

# Step 3: Remove Lambda functions
echo "⚡ Step 3: Removing Lambda functions..."
AUDIO_LAMBDA_FUNCTIONS=(
    "${PROJECT_PREFIX}-audio_ingest"
    "${PROJECT_PREFIX}-audio_analyze"
    "${PROJECT_PREFIX}-index_audio"
)

for func_name in "${AUDIO_LAMBDA_FUNCTIONS[@]}"; do
    if aws lambda get-function --function-name "$func_name" --region "$REGION" &>/dev/null; then
        # Delete the function
        aws lambda delete-function \
            --function-name "$func_name" \
            --region "$REGION" 2>/dev/null

        echo "   ✅ Removed Lambda function: $func_name"
    else
        echo "   ℹ️  Lambda function not found: $func_name"
    fi
done
echo ""

# Step 4: Remove Lambda layers (if they exist)
echo "📦 Step 4: Removing Lambda layers..."
AUDIO_LAYER_NAME="${PROJECT_PREFIX}-audio-dependencies"

# Get all versions of the layer
LAYER_VERSIONS=$(aws lambda list-layer-versions \
    --layer-name "$AUDIO_LAYER_NAME" \
    --region "$REGION" \
    --query 'LayerVersions[].Version' \
    --output text 2>/dev/null || echo "")

if [ -n "$LAYER_VERSIONS" ]; then
    for version in $LAYER_VERSIONS; do
        aws lambda delete-layer-version \
            --layer-name "$AUDIO_LAYER_NAME" \
            --version-number "$version" \
            --region "$REGION" 2>/dev/null || true
    done
    echo "   ✅ Removed Lambda layer versions: $AUDIO_LAYER_NAME"
else
    echo "   ℹ️  Lambda layer not found: $AUDIO_LAYER_NAME"
fi
echo ""

# Step 5: Remove S3 buckets (audio buckets)
echo "🪣 Step 5: Removing S3 buckets..."
# List all buckets with the audio prefix
AUDIO_BUCKETS=$(aws s3api list-buckets \
    --query "Buckets[?starts_with(Name, '${PROJECT_PREFIX}-audio-')].Name" \
    --output text \
    --region "$REGION" 2>/dev/null || echo "")

if [ -n "$AUDIO_BUCKETS" ]; then
    for bucket in $AUDIO_BUCKETS; do
        echo "   Removing bucket: $bucket"

        # Empty the bucket first
        aws s3 rm "s3://${bucket}" --recursive --region "$REGION" 2>/dev/null || true

        # Delete the bucket
        aws s3api delete-bucket \
            --bucket "$bucket" \
            --region "$REGION" 2>/dev/null || true

        echo "   ✅ Removed S3 bucket: $bucket"
    done
else
    echo "   ℹ️  No audio S3 buckets found"
fi
echo ""

# Step 6: Clean up DynamoDB (optional - only if you want to remove audio records)
echo "🗄️  Step 6: DynamoDB cleanup..."
echo "   ℹ️  Note: DynamoDB table is shared with video pipeline, so we won't delete it."
echo "   ℹ️  Audio records in the table will remain but won't affect video pipeline."
echo "   ℹ️  If you want to remove audio records, you can query and delete them manually."
echo ""

# Summary
echo "=============================================="
echo -e "${GREEN}✅ Audio pipeline cleanup complete!${NC}"
echo "=============================================="
echo ""
echo "Removed resources:"
echo "  ✅ EventBridge rules"
echo "  ✅ Step Functions state machines"
echo "  ✅ Lambda functions (audio_ingest, audio_analyze, index_audio)"
echo "  ✅ Lambda layers (audio-dependencies)"
echo "  ✅ S3 buckets (audio-*)"
echo ""
echo "Note: DynamoDB table and IAM roles were not deleted as they are shared with video pipeline."
