"""Streamlit dashboard for video pipeline monitoring."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

import streamlit as st

from shared.aws import S3Storage, build_aws_resources, trigger_state_machine
from shared.config import get_runtime_config
from shared.index import query_processed_media

# Page config
st.set_page_config(
    page_title="Video Pipeline Dashboard",
    page_icon="🎬",
    layout="wide",
)

# Predefined campaigns that work well
PREDEFINED_CAMPAIGNS = [
    "nature",
    "tech",
    "travel",
    "animals",
    "landscape",
]

# Default campaign
DEFAULT_CAMPAIGN = "nature"

# Initialize session state
if "campaign" not in st.session_state:
    st.session_state.campaign = DEFAULT_CAMPAIGN
if "batch_size_video" not in st.session_state:
    st.session_state.batch_size_video = 2


def get_s3_storage():
    """Get S3 storage client."""
    runtime_config = get_runtime_config()
    resources = build_aws_resources(aws_config=runtime_config.aws)
    return S3Storage(resources["s3"])


def list_campaigns() -> list[str]:
    """List available campaigns (themes/tags) from S3, filtering out API source names."""
    try:
        storage = get_s3_storage()
        runtime_config = get_runtime_config()
        campaigns = set()

        # List video campaigns (Wikimedia/Pixabay)
        for key in storage.list_keys(
            bucket=runtime_config.aws.video_bucket, prefix="media-raw/video/"
        ):
            parts = key.split("/")
            if len(parts) >= 4:  # media-raw/video/{source}/{campaign}/
                campaign = parts[3]
                # Filter out API names, only include valid themes
                if campaign not in {"internetarchive", "wikimedia", "pixabay"}:
                    campaigns.add(campaign)

        # Merge with predefined campaigns and return sorted
        all_campaigns = campaigns.union(set(PREDEFINED_CAMPAIGNS))
        return sorted(list(all_campaigns))
    except Exception:
        # Fallback to predefined campaigns if S3 access fails
        return PREDEFINED_CAMPAIGNS


def get_recent_executions(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent video pipeline executions from Step Functions."""
    try:
        runtime_config = get_runtime_config()
        resources = build_aws_resources(aws_config=runtime_config.aws)
        stepfunctions = resources["stepfunctions"]

        executions = []

        # Get video pipeline executions
        video_sm_arn = os.environ.get("MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN")
        if video_sm_arn:
            try:
                response = stepfunctions.list_executions(
                    stateMachineArn=video_sm_arn,
                    maxResults=limit,
                )
                for exec_item in response.get("executions", []):
                    exec_arn = exec_item["executionArn"]
                    exec_details = stepfunctions.describe_execution(executionArn=exec_arn)
                    input_data = json.loads(exec_details.get("input", "{}"))
                    output_data = (
                        json.loads(exec_details.get("output", "{}"))
                        if exec_details.get("output")
                        else {}
                    )

                    start_date = exec_item["startDate"]
                    if isinstance(start_date, datetime):
                        timestamp_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        timestamp_str = str(start_date).replace("T", " ").split(".")[0]

                    # Get processed count from finalization step (this is the REAL number of processed files)
                    # The FinalizeResults step stores its output in $.finalization
                    finalization_processed = output_data.get("finalization", {}).get(
                        "processed_count", 0
                    )
                    # Use finalization.processed_count as the source of truth
                    files_processed = finalization_processed

                    # Get ingested videos metadata
                    ingested_videos = output_data.get("metadata", [])
                    ingested_by_source = output_data.get("metadata_by_source", {})

                    # Get processed videos from finalization results
                    processed_videos = output_data.get("finalization", {}).get("results", [])

                    executions.append(
                        {
                            "timestamp": timestamp_str,
                            "timestamp_obj": exec_item["startDate"],
                            "campaign": input_data.get("campaign", "unknown"),
                            "type": "video",
                            "batch_size": input_data.get("batch_size_video", 0),
                            "status": exec_item["status"],
                            "files_processed": files_processed,
                            "execution_arn": exec_arn,
                            "ingested_videos": ingested_videos,
                            "ingested_by_source": ingested_by_source,
                            "processed_videos": processed_videos,
                        }
                    )
            except Exception as e:
                st.error(f"Error fetching video executions: {e}")

        # Sort by timestamp descending (most recent first)
        executions.sort(key=lambda x: x["timestamp_obj"], reverse=True)
        return executions[:limit]

    except Exception as e:
        st.error(f"Error fetching executions: {e}")
        return []


def get_pipeline_stats() -> dict[str, int]:
    """Get aggregated statistics for video pipeline, across all campaigns."""
    try:
        runtime_config = get_runtime_config()
        storage = get_s3_storage()

        # Query all indexed video media
        all_records = query_processed_media(media_type="video", limit=10000)

        # Count all raw video files by source (across all campaigns)
        video_raw_wikimedia = sum(
            1
            for key in storage.list_keys(
                bucket=runtime_config.aws.video_bucket,
                prefix="media-raw/video/wikimedia/",
            )
            if not key.endswith("/")
        )
        video_raw_pixabay = sum(
            1
            for key in storage.list_keys(
                bucket=runtime_config.aws.video_bucket,
                prefix="media-raw/video/pixabay/",
            )
            if not key.endswith("/")
        )
        video_raw_total = video_raw_wikimedia + video_raw_pixabay

        # Count processed by source
        video_processed_wikimedia = sum(1 for r in all_records if "wikimedia" in r.s3_key)
        video_processed_pixabay = sum(1 for r in all_records if "pixabay" in r.s3_key)
        video_processed_total = len(all_records)

        return {
            "raw_total": video_raw_total,
            "processed_total": video_processed_total,
            "raw_wikimedia": video_raw_wikimedia,
            "processed_wikimedia": video_processed_wikimedia,
            "raw_pixabay": video_raw_pixabay,
            "processed_pixabay": video_processed_pixabay,
        }
    except Exception as e:
        st.error(f"Error getting pipeline stats: {e}")
        return {
            "raw_total": 0,
            "processed_total": 0,
            "raw_wikimedia": 0,
            "processed_wikimedia": 0,
            "raw_pixabay": 0,
            "processed_pixabay": 0,
        }


# Main dashboard
st.title("🎬 Video Pipeline Dashboard")

# Sidebar for controls
with st.sidebar:
    st.header("Controls")

    campaigns = list_campaigns()
    selected_campaign = st.selectbox(
        "Campaign (theme/tag)",
        options=campaigns,
        index=campaigns.index(st.session_state.campaign)
        if st.session_state.campaign in campaigns
        else 0,
        help="Select a predefined campaign that works well, or type a custom one below",
    )

    # Allow custom campaign input
    custom_campaign = st.text_input(
        "Or enter custom campaign",
        value="" if selected_campaign in PREDEFINED_CAMPAIGNS else selected_campaign,
        help="Leave empty to use selected campaign above",
    )

    # Use custom if provided, otherwise use selected
    if custom_campaign and custom_campaign.strip():
        st.session_state.campaign = custom_campaign.lower().strip()
    else:
        st.session_state.campaign = selected_campaign

    st.session_state.batch_size_video = st.slider(
        "Batch Size",
        min_value=1,
        max_value=10,
        value=st.session_state.batch_size_video,
    )

    st.divider()

    # Trigger button
    if st.button("🎥 Run Video Pipeline", type="primary", use_container_width=True):
        try:
            runtime_config = get_runtime_config()
            video_sm_arn = os.environ.get("MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN")
            if not video_sm_arn:
                st.error("Video State Machine ARN not configured")
            else:
                payload = {
                    "campaign": st.session_state.campaign,
                    "batch_size_video": st.session_state.batch_size_video,
                }
                result = trigger_state_machine(
                    name=video_sm_arn,
                    payload=payload,
                    aws_config=runtime_config.aws,
                )
                st.success("✅ Triggered!")
                st.balloons()
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()

    # About section (compact, below button)
    with st.expander("ℹ️ About", expanded=False):
        st.markdown("""
        **Video processing pipeline** that ingests Creative Commons videos from Wikimedia Commons and Pixabay, analyzes them with Amazon Rekognition, and stores metadata in DynamoDB.

        **Workflow:** Ingest → Process (Rekognition) → Index

        **Automated:** Runs weekly on Mondays via EventBridge.
        """)

# Main content - Overall Statistics (without title)
pipeline_stats = get_pipeline_stats()

col1, col2 = st.columns(2)
raw_total = pipeline_stats.get("raw_total", 0)
processed_total = pipeline_stats.get("processed_total", 0)

with col1:
    st.metric("Total Raw Files", raw_total)
with col2:
    st.metric("Total Processed Files", processed_total)

st.markdown("#### By Source")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Wikimedia - Raw", pipeline_stats.get("raw_wikimedia", 0))
with col2:
    st.metric("Wikimedia - Processed", pipeline_stats.get("processed_wikimedia", 0))
with col3:
    st.metric("Pixabay - Raw", pipeline_stats.get("raw_pixabay", 0))
with col4:
    st.metric("Pixabay - Processed", pipeline_stats.get("processed_pixabay", 0))

st.divider()

# Recent executions table
st.markdown("### 📋 Recent VIDEO Executions")
recent_executions = get_recent_executions(limit=10)

# Check if there are running executions for auto-refresh
has_running = False
if recent_executions:
    has_running = any(e["status"] == "RUNNING" for e in recent_executions)
    if has_running:
        # Show auto-refresh indicator
        st.info("🔄 Execution in progress... Page will auto-refresh")

        # Use Streamlit's built-in auto-refresh mechanism
        # This will refresh the page after 5 seconds if there's a running execution
        time.sleep(5)
        st.rerun()

if recent_executions:
    # Extract execution ID from ARN
    for exec_item in recent_executions:
        arn = exec_item.get("execution_arn", "")
        if arn:
            # Extract UUID from ARN (last part after last colon)
            exec_id = arn.split(":")[-1]
            exec_item["execution_id"] = exec_id

    df_data = []
    for exec_item in recent_executions:
        status = exec_item["status"]
        # Add icon and color based on status
        if status == "SUCCEEDED":
            status_display = "✅ SUCCEEDED"
        elif status == "FAILED":
            status_display = "❌ FAILED"
        elif status == "RUNNING":
            status_display = "🔄 RUNNING"
        elif status == "TIMED_OUT":
            status_display = "⏱️ TIMED_OUT"
        elif status == "ABORTED":
            status_display = "🛑 ABORTED"
        else:
            status_display = f"❓ {status}"

        df_data.append(
            {
                "Time": exec_item["timestamp"],
                "Campaign": exec_item["campaign"],
                "Batch Size": exec_item["batch_size"],
                "Status": status_display,
                "Files Processed": exec_item["files_processed"],
                "Execution ID": exec_item.get("execution_id", ""),
            }
        )

    import pandas as pd

    df = pd.DataFrame(df_data)

    # Style the dataframe with colors
    def style_status(val):
        if "✅" in str(val):
            return "color: #00ff00; font-weight: bold"
        elif "❌" in str(val):
            return "color: #ff4444; font-weight: bold"
        elif "🔄" in str(val):
            return "color: #4488ff; font-weight: bold"
        elif "⏱️" in str(val):
            return "color: #ffaa00; font-weight: bold"
        elif "🛑" in str(val):
            return "color: #aa0000; font-weight: bold"
        return ""

    styled_df = df.style.applymap(style_status, subset=["Status"])
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No executions found")

st.divider()

# Last execution summary (compact, after table)
recent_executions_summary = get_recent_executions(limit=1)
if recent_executions_summary:
    last_exec = recent_executions_summary[0]

    # Extract execution ID from ARN if not already present
    if "execution_id" not in last_exec or not last_exec.get("execution_id"):
        arn = last_exec.get("execution_arn", "")
        if arn:
            exec_id = arn.split(":")[-1]
            last_exec["execution_id"] = exec_id

    status = last_exec["status"]

    # Status display with icon (compact)
    if status == "SUCCEEDED":
        status_icon = "✅"
        status_color = "#00ff00"
    elif status == "FAILED":
        status_icon = "❌"
        status_color = "#ff4444"
    elif status == "RUNNING":
        status_icon = "🔄"
        status_color = "#4488ff"
    elif status == "TIMED_OUT":
        status_icon = "⏱️"
        status_color = "#ffaa00"
    elif status == "ABORTED":
        status_icon = "🛑"
        status_color = "#aa0000"
    else:
        status_icon = "❓"
        status_color = "#888888"

    st.markdown("### 📊 Last Execution Summary")

    # Compact display
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.write(
            f'<span style="color: {status_color}; font-size: 14px;">{status_icon} <strong>{status}</strong></span>',
            unsafe_allow_html=True,
        )

    with col2:
        st.write(f"**Campaign:** {last_exec['campaign']}")

    with col3:
        st.write(f"**Batch Size:** {last_exec['batch_size']}")

    with col4:
        st.write(f"**Files Processed:** {last_exec['files_processed']}")

    # Show videos received and processed
    ingested_videos = last_exec.get("ingested_videos", [])
    ingested_by_source = last_exec.get("ingested_by_source", {})
    processed_videos = last_exec.get("processed_videos", [])

    if ingested_videos or ingested_by_source:
        st.markdown("#### 📥 Videos Received")

        # Show by source if available
        if ingested_by_source:
            for source_name, videos in ingested_by_source.items():
                if videos:
                    st.write(f"**{source_name.capitalize()}:** {len(videos)} video(s)")
                    with st.expander(f"View {source_name} videos ({len(videos)})", expanded=False):
                        for video in videos:
                            video_title = video.get("title", "Untitled")
                            source_id = video.get("source_id", "")
                            st.write(f"- **{video_title}** (ID: {source_id})")
        else:
            st.write(f"**Total:** {len(ingested_videos)} video(s)")
            with st.expander(f"View videos ({len(ingested_videos)})", expanded=False):
                for video in ingested_videos:
                    video_title = video.get("title", "Untitled")
                    source_id = video.get("source_id", "")
                    st.write(f"- **{video_title}** (ID: {source_id})")

    if processed_videos:
        st.markdown("#### ✅ Videos Processed")
        st.write(f"**Total:** {len(processed_videos)} video(s)")
        with st.expander(f"View processed videos ({len(processed_videos)})", expanded=False):
            for result in processed_videos:
                video_s3_key = result.get("video_s3_key", "")
                video_name = video_s3_key.split("/")[-1] if video_s3_key else "Unknown"
                summary = result.get("summary", {})
                labels_count = summary.get("total_labels", 0)
                st.write(f"- **{video_name}** ({labels_count} labels detected)")

    # Show execution details in expander
    with st.expander("📋 Execution Details", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Time:**", last_exec["timestamp"])
            st.write("**Execution ID:**", last_exec.get("execution_id", "N/A"))
        with col2:
            st.write(
                "**Status:**",
                f'<span style="color: {status_color}; font-weight: bold;">{status_icon} {status}</span>',
                unsafe_allow_html=True,
            )
            if last_exec["files_processed"] > 0:
                st.write(
                    "**Result:**",
                    f"✅ Successfully processed {last_exec['files_processed']} video(s)",
                )
            elif status == "FAILED":
                st.write("**Result:**", "❌ Execution failed")
            elif status == "RUNNING":
                st.write("**Result:**", "🔄 Processing in progress...")

st.divider()

# Processed files
st.markdown("### 📁 Processed Files (VIDEO)")
all_records = query_processed_media(media_type="video", limit=100)

if all_records:
    # Group by campaign
    campaigns_found = sorted(set(r.campaign for r in all_records))

    selected_campaign_view = st.selectbox(
        "Filter by Campaign",
        options=["All"] + campaigns_found,
        index=0,
    )

    if selected_campaign_view != "All":
        filtered_records = [r for r in all_records if r.campaign == selected_campaign_view]
    else:
        filtered_records = all_records

    # Separate by source
    wikimedia_records = [r for r in filtered_records if "wikimedia" in r.s3_key]
    pixabay_records = [r for r in filtered_records if "pixabay" in r.s3_key]

    tab1, tab2 = st.tabs(["Wikimedia", "Pixabay"])

    with tab1:
        if wikimedia_records:
            for record in wikimedia_records[:20]:  # Limit to 20 for performance
                with st.expander(f"📹 {record.s3_key.split('/')[-1]}"):
                    st.json(record.metadata)
        else:
            st.info("No Wikimedia videos processed yet")

    with tab2:
        if pixabay_records:
            for record in pixabay_records[:20]:  # Limit to 20 for performance
                with st.expander(f"📹 {record.s3_key.split('/')[-1]}"):
                    st.json(record.metadata)
        else:
            st.info("No Pixabay videos processed yet")
else:
    st.info("No video files processed yet")
