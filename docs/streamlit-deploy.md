# Streamlit Cloud Deployment Guide

## Prerequisites

1. GitHub repository with the code pushed
2. Streamlit Cloud account (free tier available)
3. AWS credentials configured as secrets

## Deployment Steps

### 1. Connect Repository to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your GitHub repository: `andresgfranco/media-pipelines`
4. Set main file path: `dashboard/app.py`
5. Set app URL (optional)

### 2. Configure Secrets

In Streamlit Cloud, add the following secrets via the app settings:

```toml
# .streamlit/secrets.toml (configured in Streamlit Cloud dashboard)
AWS_ACCESS_KEY_ID = "your-access-key"
AWS_SECRET_ACCESS_KEY = "your-secret-key"
AWS_DEFAULT_REGION = "us-east-1"

MEDIA_PIPELINES_VIDEO_BUCKET = "your-video-bucket"
MEDIA_PIPELINES_METADATA_TABLE = "your-metadata-table"
MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN = "arn:aws:states:..."
MEDIA_PIPELINES_AWS_REGION = "us-east-1"
```

### 3. Configure App Settings

- **Python version**: 3.11
- **Main file**: `dashboard/app.py`
- **Command**: Leave default (Streamlit Cloud will detect `app.py`)

### 4. Deploy

Click "Deploy" and wait for the app to build and launch.

## Local Development

To run the dashboard locally:

```bash
# Install dependencies
pip install -e '.[dashboard]'

# Set environment variables
export MEDIA_PIPELINES_VIDEO_BUCKET=your-bucket
export MEDIA_PIPELINES_METADATA_TABLE=your-table
export MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN=arn:aws:states:...
export MEDIA_PIPELINES_AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret

# Run Streamlit
streamlit run dashboard/app.py
```

## Troubleshooting

- **Import errors**: Ensure all dependencies are in `pyproject.toml`
- **AWS connection errors**: Verify credentials are set correctly in Streamlit Cloud secrets
- **S3 access errors**: Check IAM permissions for the AWS credentials
