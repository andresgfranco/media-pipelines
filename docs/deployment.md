# Deployment Guide

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed (for Lambda deployment) OR Terraform/CDK configured
- Python 3.11+ for packaging Lambda functions
- Access to create: S3 buckets, Lambda functions, Step Functions, DynamoDB tables, EventBridge rules, SNS topics

## Step 1: Create AWS Resources

### S3 Buckets

```bash
# Create audio bucket
aws s3 mb s3://media-pipelines-audio-$(date +%s) --region us-east-1

# Create video bucket
aws s3 mb s3://media-pipelines-video-$(date +%s) --region us-east-1
```

### DynamoDB Table

```bash
aws dynamodb create-table \
  --table-name media-pipelines-metadata \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### SNS Topic (Optional)

```bash
aws sns create-topic \
  --name media-pipelines-notifications \
  --region us-east-1
```

## Step 2: Package Lambda Functions

### Install Dependencies

```bash
# Create deployment package directory
mkdir -p deploy

# Install dependencies for Lambda (Python 3.11)
pip install -r requirements.txt -t deploy/
```

### Package Each Lambda Function

For each handler in `infrastructure/handlers/`, create a deployment package:

```bash
# Example for audio_ingest
cd deploy
zip -r ../lambda-audio-ingest.zip .
cd ..
zip -g lambda-audio-ingest.zip infrastructure/handlers/audio_ingest.py
zip -g lambda-audio-ingest.zip audio_pipeline/ingest.py
zip -g lambda-audio-ingest.zip shared/
```

## Step 3: Deploy Lambda Functions

```bash
# Create Lambda function
aws lambda create-function \
  --function-name media-pipelines-audio-ingest \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role \
  --handler infrastructure.handlers.audio_ingest.handler \
  --zip-file fileb://lambda-audio-ingest.zip \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables="{
    MEDIA_PIPELINES_AUDIO_BUCKET=your-audio-bucket,
    MEDIA_PIPELINES_VIDEO_BUCKET=your-video-bucket,
    MEDIA_PIPELINES_METADATA_TABLE=media-pipelines-metadata,
    MEDIA_PIPELINES_AWS_REGION=us-east-1
  }"
```

Repeat for all handlers:
- `audio_ingest`
- `audio_analyze`
- `video_ingest`
- `video_rekognition_start`
- `video_rekognition_check`
- `video_rekognition_finalize`
- `index_audio`
- `index_video`

## Step 4: Deploy Step Functions State Machines

### Audio Pipeline

```bash
# Replace function ARNs in the JSON
sed 's/${IngestAudioFunctionArn}/arn:aws:lambda:REGION:ACCOUNT:function:media-pipelines-audio-ingest/g' \
  infrastructure/audio_state_machine.asl.json | \
sed 's/${AnalyzeAudioFunctionArn}/arn:aws:lambda:REGION:ACCOUNT:function:media-pipelines-audio-analyze/g' | \
sed 's/${IndexAudioFunctionArn}/arn:aws:lambda:REGION:ACCOUNT:function:media-pipelines-index-audio/g' > audio_sm.json

aws stepfunctions create-state-machine \
  --name AudioPipelineStateMachine \
  --definition file://audio_sm.json \
  --role-arn arn:aws:iam::ACCOUNT_ID:role/stepfunctions-execution-role
```

### Video Pipeline

Similar process for `video_state_machine.asl.json`.

## Step 5: Configure EventBridge Rules

See [scheduling.md](scheduling.md) for EventBridge configuration.

## Step 6: Set Up IAM Roles

### Lambda Execution Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::media-pipelines-audio-*",
        "arn:aws:s3:::media-pipelines-video-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Scan",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/media-pipelines-metadata"
    },
    {
      "Effect": "Allow",
      "Action": [
        "rekognition:StartLabelDetection",
        "rekognition:GetLabelDetection"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:*:*:media-pipelines-notifications"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### Step Functions Execution Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": [
        "arn:aws:lambda:*:*:function:media-pipelines-*"
      ]
    }
  ]
}
```

## Step 7: Deploy Streamlit Dashboard

See [streamlit-deploy.md](streamlit-deploy.md) for Streamlit Cloud deployment.

## Step 8: Test Deployment

```bash
# Test audio pipeline
python infrastructure/schedule_trigger.py audio nature 1

# Test video pipeline
python infrastructure/schedule_trigger.py video nature 1

# Run smoke tests
pytest tests/smoke_test.py -v
```

## Troubleshooting

- **Lambda timeout**: Increase timeout or optimize code
- **Permission errors**: Check IAM roles and policies
- **Import errors**: Ensure all dependencies are packaged
- **Step Functions errors**: Check CloudWatch Logs for detailed error messages
