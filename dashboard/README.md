# Media Pipelines Dashboard

Streamlit dashboard for monitoring and triggering media pipelines.

## Features

- **Manual Pipeline Triggers**: Trigger video pipeline with custom campaigns and batch sizes
- **Execution History**: View recent pipeline executions with status, timestamps, and results
- **Asset Monitoring**: Track raw and processed files per campaign, separated by source (Wikimedia/Pixabay for video)
- **File Browser**: Explore processed media files with metadata and labels
- **Real-time Updates**: Dashboard refreshes to show latest pipeline status

## Setup

### 1. Install Dependencies

```bash
pip install streamlit boto3
```

### 2. Configure Environment Variables

The dashboard needs AWS credentials and Step Functions ARNs. You can either:

**Option A: Use `.aws-deployment-config` file** (created by `deploy_to_aws.sh`):
```bash
source .aws-deployment-config
```

**Option B: Set environment variables manually**:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Get these from your deployment output or AWS Console
export MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN=arn:aws:states:...

# Optional: If using custom bucket/table names
export MEDIA_PIPELINES_VIDEO_BUCKET=media-pipelines-video-...
export MEDIA_PIPELINES_METADATA_TABLE=media-pipelines-metadata
```

### 3. Run the Dashboard

```bash
streamlit run dashboard/app.py
```

Or use the provided script:
```bash
./dashboard/streamlit_app.sh
```

The dashboard will open in your browser at `http://localhost:8501`

## Usage

### Triggering Pipelines

1. Select a campaign from the dropdown (or type a new one)
2. Adjust batch size using the slider
3. Click "Run Video Pipeline"
4. The dashboard will show a success message with the execution ARN

### Viewing Executions

- Recent executions appear in the "Recent Executions" table
- Click "Show execution details" to see full execution input/output
- Status indicators:
  - 🟢 SUCCEEDED
  - 🟡 RUNNING
  - 🔴 FAILED
  - 🟠 TIMED_OUT
  - ⚫ ABORTED

### Exploring Files

- Use the "Processed Media Files" section to browse files by type and source
- Expand each file to see:
  - S3 keys (raw and processed)
  - Ingestion and processing timestamps
  - Metadata (audio features, video labels, etc.)

### Monitoring Assets

- Metrics show raw vs processed file counts
- Video pipeline shows separate counts for Wikimedia and Pixabay sources
- Counts update automatically as pipelines process new files

## Troubleshooting

**"State Machine ARN not configured"**
- Make sure `MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN` is set
- Check `.aws-deployment-config` or get ARN from AWS Console

**"No executions yet"**
- Trigger a pipeline first
- Check that Step Functions have permission to list executions

**"Error fetching executions"**
- Verify AWS credentials are configured correctly
- Check IAM permissions for Step Functions `ListExecutions` and `DescribeExecution`

**Dashboard shows no files**
- Make sure pipelines have been run at least once
- Check that DynamoDB table exists and has records
- Verify S3 bucket names are correct

## Deployment

For production deployment, consider:

- **Streamlit Community Cloud**: Free hosting for Streamlit apps
- **AWS App Runner**: Containerized deployment
- **AWS Fargate**: ECS task running Streamlit
- **EC2**: Traditional server deployment

See `docs/streamlit-deploy.md` for detailed deployment instructions.
