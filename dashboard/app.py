"""Streamlit dashboard for media pipelines monitoring."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from shared.aws import S3Storage, build_aws_resources
from shared.config import get_runtime_config

# Page config
st.set_page_config(
    page_title="Media Pipelines Dashboard",
    page_icon="🎬",
    layout="wide",
)

# Initialize session state
if "campaign" not in st.session_state:
    st.session_state.campaign = "nature"
if "batch_size_audio" not in st.session_state:
    st.session_state.batch_size_audio = 5
if "batch_size_video" not in st.session_state:
    st.session_state.batch_size_video = 2


def get_s3_storage():
    """Get S3 storage client."""
    runtime_config = get_runtime_config()
    resources = build_aws_resources(aws_config=runtime_config.aws)
    return S3Storage(resources["s3"])


def list_campaigns() -> list[str]:
    """List available campaigns from S3."""
    try:
        storage = get_s3_storage()
        runtime_config = get_runtime_config()
        campaigns = set()

        # List audio campaigns
        for key in storage.list_keys(
            bucket=runtime_config.aws.audio_bucket, prefix="media-raw/audio/"
        ):
            parts = key.split("/")
            if len(parts) >= 3:
                campaigns.add(parts[2])

        # List video campaigns
        for key in storage.list_keys(
            bucket=runtime_config.aws.video_bucket, prefix="media-raw/video/"
        ):
            parts = key.split("/")
            if len(parts) >= 3:
                campaigns.add(parts[2])

        return sorted(list(campaigns)) if campaigns else ["nature", "tech", "travel"]
    except Exception:
        # Fallback to default campaigns if S3 access fails
        return ["nature", "tech", "travel"]


def get_recent_executions(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent pipeline executions (mock for now)."""
    # TODO: Integrate with Step Functions execution history or DynamoDB
    return [
        {
            "timestamp": "2024-01-15 10:30:00",
            "campaign": "nature",
            "type": "audio",
            "batch_size": 5,
            "status": "SUCCEEDED",
            "files_processed": 5,
        },
        {
            "timestamp": "2024-01-15 10:25:00",
            "campaign": "nature",
            "type": "video",
            "batch_size": 2,
            "status": "SUCCEEDED",
            "files_processed": 2,
        },
    ]


def get_asset_counts(campaign: str) -> dict[str, int]:
    """Get asset counts for a campaign."""
    try:
        storage = get_s3_storage()
        runtime_config = get_runtime_config()

        audio_raw = sum(
            1
            for _ in storage.list_keys(
                bucket=runtime_config.aws.audio_bucket,
                prefix=f"media-raw/audio/{campaign}/",
            )
        )
        audio_processed = sum(
            1
            for _ in storage.list_keys(
                bucket=runtime_config.aws.audio_bucket,
                prefix=f"media-processed/audio/{campaign}/",
            )
        )
        video_raw = sum(
            1
            for _ in storage.list_keys(
                bucket=runtime_config.aws.video_bucket,
                prefix=f"media-raw/video/{campaign}/",
            )
        )
        video_processed = sum(
            1
            for _ in storage.list_keys(
                bucket=runtime_config.aws.video_bucket,
                prefix=f"media-processed/video/{campaign}/",
            )
        )

        return {
            "audio_raw": audio_raw,
            "audio_processed": audio_processed,
            "video_raw": video_raw,
            "video_processed": video_processed,
        }
    except Exception:
        return {
            "audio_raw": 0,
            "audio_processed": 0,
            "video_raw": 0,
            "video_processed": 0,
        }


def get_latest_summary(campaign: str, media_type: str) -> dict[str, Any] | None:
    """Get latest summary JSON for a campaign."""
    try:
        storage = get_s3_storage()
        runtime_config = get_runtime_config()
        bucket = (
            runtime_config.aws.audio_bucket
            if media_type == "audio"
            else runtime_config.aws.video_bucket
        )

        prefix = f"media-processed/{media_type}/{campaign}/"
        keys = list(storage.list_keys(bucket=bucket, prefix=prefix))

        if not keys:
            return None

        # Get the most recent summary
        latest_key = sorted(keys)[-1]

        # Download and parse JSON
        s3_client = build_aws_resources(aws_config=runtime_config.aws)["s3"]
        response = s3_client.get_object(Bucket=bucket, Key=latest_key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception:
        return None


# Main dashboard
st.title("🎬 Media Pipelines Dashboard")

# Sidebar for controls
with st.sidebar:
    st.header("Pipeline Controls")

    campaigns = list_campaigns()
    selected_campaign = st.selectbox(
        "Campaign",
        campaigns,
        index=(
            campaigns.index(st.session_state.campaign)
            if st.session_state.campaign in campaigns
            else 0
        ),
    )
    st.session_state.campaign = selected_campaign

    st.session_state.batch_size_audio = st.slider(
        "Audio Batch Size",
        min_value=1,
        max_value=20,
        value=st.session_state.batch_size_audio,
    )

    st.session_state.batch_size_video = st.slider(
        "Video Batch Size",
        min_value=1,
        max_value=10,
        value=st.session_state.batch_size_video,
    )

    st.divider()

    if st.button("🚀 Run Audio Pipeline", type="primary", use_container_width=True):
        st.info("Audio pipeline execution triggered!")
        # TODO: Trigger Step Functions execution

    if st.button("🎥 Run Video Pipeline", type="primary", use_container_width=True):
        st.info("Video pipeline execution triggered!")
        # TODO: Trigger Step Functions execution

# Main content
col1, col2, col3, col4 = st.columns(4)

asset_counts = get_asset_counts(st.session_state.campaign)

with col1:
    st.metric("Audio Raw", asset_counts["audio_raw"])

with col2:
    st.metric("Audio Processed", asset_counts["audio_processed"])

with col3:
    st.metric("Video Raw", asset_counts["video_raw"])

with col4:
    st.metric("Video Processed", asset_counts["video_processed"])

st.divider()

# Recent executions
st.subheader("Recent Executions")
executions = get_recent_executions()
if executions:
    st.dataframe(
        executions,
        use_container_width=True,
        column_config={
            "timestamp": "Timestamp",
            "campaign": "Campaign",
            "type": "Type",
            "batch_size": "Batch Size",
            "status": "Status",
            "files_processed": "Files Processed",
        },
    )
else:
    st.info("No executions yet")

st.divider()

# Latest summaries
col1, col2 = st.columns(2)

with col1:
    st.subheader("Latest Audio Summary")
    audio_summary = get_latest_summary(st.session_state.campaign, "audio")
    if audio_summary:
        st.json(audio_summary)
    else:
        st.info("No audio summaries available")

with col2:
    st.subheader("Latest Video Summary")
    video_summary = get_latest_summary(st.session_state.campaign, "video")
    if video_summary:
        st.json(video_summary)
    else:
        st.info("No video summaries available")
