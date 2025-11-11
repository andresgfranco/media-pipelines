# AWS Deployment Guide

This guide will help you deploy the Media Pipelines to your AWS account.

## Prerequisites

1. **AWS CLI configured** with appropriate credentials:
   ```bash
   aws configure
   ```

2. **Required environment variables** (optional, but recommended):
   ```bash
   export PIXABAY_API_KEY="your-pixabay-api-key"  # For Pixabay video source
   # Note: Audio uses Internet Archive which doesn't require an API key
   ```

3. **Python 3.11+** with pip installed

## Quick Deployment

1. **Option A: Deploy with Pixabay API key pre-configured**:
   ```bash
   ./scripts/deploy_with_pixabay.sh
   ```

2. **Option B: Deploy manually with your own API key**:
   ```bash
   export PIXABAY_API_KEY="your-pixabay-api-key"
   ./scripts/deploy_to_aws.sh
   ```

3. **Option C: Deploy without Pixabay** (will only use Wikimedia for video):
   ```bash
   ./scripts/deploy_to_aws.sh
   ```

   This script will:
   - Create S3 buckets for audio and video
   - Create DynamoDB table for metadata
   - Create IAM roles for Lambda and Step Functions
   - Package and deploy all Lambda functions
   - Deploy Step Functions state machines
   - Save configuration to `.aws-deployment-config`

2. **Load the configuration**:
   ```bash
   source .aws-deployment-config
   ```

3. **Test the deployment**:
   ```bash
   python scripts/test_aws_deployment.py
   ```

## Manual Testing

You can also trigger pipelines manually:

```bash
# Load configuration first
source .aws-deployment-config

# Trigger audio pipeline
python infrastructure/schedule_trigger.py audio nature 1

# Trigger video pipeline
python infrastructure/schedule_trigger.py video nature 1
```

## What Gets Created

### S3 Buckets
- `media-pipelines-audio-{timestamp}` - Raw audio files
- `media-pipelines-video-{timestamp}` - Raw video files

### DynamoDB Table
- `media-pipelines-metadata` - Metadata for processed media

### Lambda Functions
- `media-pipelines-audio_ingest`
- `media-pipelines-audio_analyze`
- `media-pipelines-index_audio`
- `media-pipelines-video_ingest`
- `media-pipelines-video_rekognition_start`
- `media-pipelines-video_rekognition_check`
- `media-pipelines-video_rekognition_finalize`
- `media-pipelines-index_video`

### Step Functions State Machines
- `media-pipelines-audio-pipeline`
- `media-pipelines-video-pipeline`

### IAM Roles
- `media-pipelines-lambda-execution-role`
- `media-pipelines-stepfunctions-execution-role`

## Troubleshooting

### Lambda Function Errors
- Check CloudWatch Logs for detailed error messages
- Verify environment variables are set correctly
- Ensure IAM roles have proper permissions

### Step Functions Errors
- Check execution history in AWS Console
- Verify Lambda function ARNs are correct in state machine definition
- Check IAM role permissions

### Missing API Keys
- Pixabay: Set `PIXABAY_API_KEY` environment variable before deployment (for video source)
- Note: Audio uses Internet Archive which doesn't require an API key
- You can also update Lambda function environment variables after deployment

## Next Steps

After successful deployment:
1. Monitor executions in AWS Step Functions Console
2. Check S3 buckets for ingested media files
3. Query DynamoDB table for metadata
4. Integrate with Streamlit dashboard (see `docs/streamlit-deploy.md`)
