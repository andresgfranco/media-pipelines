"""Streamlit dashboard for video pipeline monitoring."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared.aws import S3Storage, build_aws_resources, trigger_state_machine  # noqa: E402
from shared.config import get_runtime_config  # noqa: E402
from shared.index import query_processed_media  # noqa: E402

st.set_page_config(
    page_title="Video Pipeline Dashboard",
    page_icon="🎬",
    layout="wide",
)

PREDEFINED_CAMPAIGNS = [
    "nature",
    "tech",
    "travel",
    "animals",
    "landscape",
]

DEFAULT_CAMPAIGN = "nature"

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

        for key in storage.list_keys(
            bucket=runtime_config.aws.video_bucket, prefix="media-raw/video/"
        ):
            parts = key.split("/")
            if len(parts) >= 4:
                campaign = parts[3]
                if campaign not in {"internetarchive", "wikimedia", "pixabay"}:
                    campaigns.add(campaign)

        all_campaigns = campaigns.union(set(PREDEFINED_CAMPAIGNS))
        return sorted(list(all_campaigns))
    except Exception:
        return PREDEFINED_CAMPAIGNS


def get_recent_executions(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent video pipeline executions from Step Functions."""
    try:
        runtime_config = get_runtime_config()
        resources = build_aws_resources(aws_config=runtime_config.aws)
        stepfunctions = resources["stepfunctions"]

        executions = []

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

                    finalization_processed = output_data.get("finalization", {}).get(
                        "processed_count", 0
                    )
                    files_processed = finalization_processed

                    ingested_videos = output_data.get("metadata", [])
                    ingested_by_source = output_data.get("metadata_by_source", {})
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

        executions.sort(key=lambda x: x["timestamp_obj"], reverse=True)
        return executions[:limit]

    except Exception as e:
        st.error(f"Error fetching executions: {e}")
        return []


def get_execution_history(execution_arn: str) -> list[dict[str, Any]]:
    """Get detailed execution history from Step Functions."""
    try:
        runtime_config = get_runtime_config()
        resources = build_aws_resources(aws_config=runtime_config.aws)
        stepfunctions = resources["stepfunctions"]

        history = []
        paginator = stepfunctions.get_paginator("get_execution_history")

        for page in paginator.paginate(executionArn=execution_arn):
            for event in page.get("events", []):
                history.append(event)

        history.sort(key=lambda x: x.get("id", 0))

        return history
    except Exception as e:
        st.error(f"Error fetching execution history: {e}")
        return []


def parse_execution_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse Step Functions execution history into structured steps."""
    steps = []
    state_steps = {}
    current_state = None

    step_names = {
        "IngestVideo": "Ingest Videos",
        "StartRekognitionJobs": "Start Rekognition Jobs",
        "ProcessRekognitionJobs": "Process Rekognition Jobs (Map State)",
        "WaitForJob": "Wait for Job",
        "CheckJobStatus": "Check Job Status",
        "JobComplete?": "Check if Job Complete",
        "FinalizeResults": "Finalize Results",
        "IndexVideo": "Index Video",
    }

    for event in history:
        event_type = event.get("type", "")
        timestamp = event.get("timestamp", 0)

        if isinstance(timestamp, datetime):
            timestamp_dt = timestamp
        elif isinstance(timestamp, int | float):
            if timestamp > 1e10:
                timestamp_dt = datetime.fromtimestamp(timestamp / 1000)
            else:
                timestamp_dt = datetime.fromtimestamp(timestamp)
        else:
            timestamp_dt = None

        if event_type == "ExecutionStarted":
            steps.append(
                {
                    "step": "Execution Started",
                    "status": "SUCCEEDED",
                    "timestamp": timestamp_dt,
                    "details": "Step Functions execution initiated",
                    "order": 0,
                }
            )

        elif event_type == "TaskStateEntered":
            state_name = event.get("stateEnteredEventDetails", {}).get("name", "")
            current_state = state_name
            if state_name and state_name not in state_steps:
                state_steps[state_name] = {
                    "step": step_names.get(state_name, state_name),
                    "status": "RUNNING",
                    "timestamp": timestamp_dt,
                    "details": f"State: {state_name}",
                    "state_name": state_name,
                    "order": len(steps) + len(state_steps),
                }

        elif event_type == "TaskStateExited":
            state_name = event.get("stateExitedEventDetails", {}).get("name", "")
            current_state = None

        elif event_type == "LambdaFunctionScheduled":
            scheduled_details = event.get("lambdaFunctionScheduledEventDetails", {})
            resource = scheduled_details.get("resource", "")

            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING" and not step_data.get("lambda"):
                    if "lambda" in resource.lower():
                        lambda_name = resource.split(":")[-1] if ":" in resource else resource
                        step_data["lambda"] = lambda_name
                        step_data["details"] = f"Lambda: {lambda_name}"
                    break

        elif event_type == "LambdaFunctionStarted":
            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING" and not step_data.get("started_at"):
                    step_data["started_at"] = timestamp_dt
                    break

        elif event_type == "LambdaFunctionSucceeded":
            succeeded_details = event.get("lambdaFunctionSucceededEventDetails", {})
            output = succeeded_details.get("output", "{}")
            try:
                output_data = json.loads(output) if output else {}
            except Exception:
                output_data = {"raw_output": str(output)} if output else {}

            if current_state and current_state in state_steps:
                step_data = state_steps[current_state]
                step_data["status"] = "SUCCEEDED"
                step_data["completed_at"] = timestamp_dt
                if output_data:
                    step_data["output"] = output_data
            else:
                for state, step_data in state_steps.items():
                    if step_data.get("status") == "RUNNING":
                        step_data["status"] = "SUCCEEDED"
                        step_data["completed_at"] = timestamp_dt
                        if output_data:
                            step_data["output"] = output_data
                        break

        elif event_type == "LambdaFunctionFailed":
            failed_details = event.get("lambdaFunctionFailedEventDetails", {})
            error = failed_details.get("error", "Unknown error")
            cause = failed_details.get("cause", "")

            # Find the most recent running step and mark it as failed
            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING":
                    step_data["status"] = "FAILED"
                    step_data["completed_at"] = timestamp_dt
                    step_data["error"] = error
                    step_data["cause"] = cause
                    break

        elif event_type == "TaskScheduled":
            scheduled_details = event.get("taskScheduledEventDetails", {})
            resource = scheduled_details.get("resource", "")

            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING" and not step_data.get("lambda"):
                    if resource:
                        step_data["resource"] = resource
                        step_data["details"] = f"Resource: {resource}"
                    break

        elif event_type == "TaskStarted":
            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING" and not step_data.get("started_at"):
                    step_data["started_at"] = timestamp_dt
                    break

        elif event_type == "TaskSucceeded":
            succeeded_details = event.get("taskSucceededEventDetails", {})
            output = succeeded_details.get("output", "{}")
            try:
                output_data = json.loads(output) if output else {}
            except Exception:
                output_data = {}

            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING":
                    step_data["status"] = "SUCCEEDED"
                    step_data["completed_at"] = timestamp_dt
                    if output_data:
                        step_data["output"] = output_data
                    break

        elif event_type == "TaskFailed":
            failed_details = event.get("taskFailedEventDetails", {})
            error = failed_details.get("error", "Unknown error")
            cause = failed_details.get("cause", "")

            # Find the most recent running step and mark it as failed
            for state, step_data in state_steps.items():
                if step_data.get("status") == "RUNNING":
                    step_data["status"] = "FAILED"
                    step_data["completed_at"] = timestamp_dt
                    step_data["error"] = error
                    step_data["cause"] = cause
                    break

        elif event_type == "MapStateEntered":
            state_name = event.get("mapStateEnteredEventDetails", {}).get("name", "")
            current_state = state_name
            if state_name and state_name not in state_steps:
                map_details = event.get("mapStateEnteredEventDetails", {})
                input_data = map_details.get("input", "{}")
                try:
                    input_json = (
                        json.loads(input_data) if isinstance(input_data, str) else input_data
                    )
                    items_path = input_json.get("rekognition", {}).get("jobs", [])
                    items_count = len(items_path) if isinstance(items_path, list) else 0
                    details = f"Map State: Processing {items_count} job(s)"
                except Exception:
                    details = "Map State: Processing multiple items"

                state_steps[state_name] = {
                    "step": step_names.get(state_name, state_name),
                    "status": "RUNNING",
                    "timestamp": timestamp_dt,
                    "details": details,
                    "state_name": state_name,
                    "order": len(steps) + len(state_steps),
                }

        elif event_type == "MapStateSucceeded":
            map_details = event.get("mapStateSucceededEventDetails", {})
            for state, step_data in state_steps.items():
                if state == "ProcessRekognitionJobs" or "Map" in step_data.get("step", ""):
                    step_data["status"] = "SUCCEEDED"
                    step_data["completed_at"] = timestamp_dt
                    output_data = map_details.get("output", "{}")
                    try:
                        output_json = (
                            json.loads(output_data) if isinstance(output_data, str) else output_data
                        )
                        completed_jobs = output_json if isinstance(output_json, list) else []
                        if completed_jobs:
                            step_data["output"] = {"completed_count": len(completed_jobs)}
                    except Exception:
                        pass
                    break

        elif event_type == "MapIterationStarted":
            iteration_details = event.get("mapIterationStartedEventDetails", {})
            iteration_index = iteration_details.get("index", 0)
            if "ProcessRekognitionJobs" in state_steps:
                map_step = state_steps["ProcessRekognitionJobs"]
                if "iterations" not in map_step:
                    map_step["iterations"] = []
                map_step["iterations"].append(
                    {
                        "index": iteration_index,
                        "started_at": timestamp_dt,
                        "status": "RUNNING",
                    }
                )

        elif event_type == "MapIterationSucceeded":
            iteration_details = event.get("mapIterationSucceededEventDetails", {})
            iteration_index = iteration_details.get("index", 0)
            if "ProcessRekognitionJobs" in state_steps:
                map_step = state_steps["ProcessRekognitionJobs"]
                if "iterations" in map_step:
                    for iter_data in map_step["iterations"]:
                        if iter_data.get("index") == iteration_index:
                            iter_data["status"] = "SUCCEEDED"
                            iter_data["completed_at"] = timestamp_dt
                            break

        elif event_type == "MapIterationFailed":
            iteration_details = event.get("mapIterationFailedEventDetails", {})
            iteration_index = iteration_details.get("index", 0)
            error = iteration_details.get("error", "Unknown error")
            cause = iteration_details.get("cause", "")
            if "ProcessRekognitionJobs" in state_steps:
                map_step = state_steps["ProcessRekognitionJobs"]
                if "iterations" in map_step:
                    for iter_data in map_step["iterations"]:
                        if iter_data.get("index") == iteration_index:
                            iter_data["status"] = "FAILED"
                            iter_data["completed_at"] = timestamp_dt
                            iter_data["error"] = error
                            iter_data["cause"] = cause
                            break

        elif event_type == "WaitStateEntered":
            wait_details = event.get("waitStateEnteredEventDetails", {})
            seconds = wait_details.get("seconds", 0)
            if seconds:
                wait_state_name = wait_details.get("name", "WaitForJob")
                if wait_state_name not in state_steps:
                    state_steps[wait_state_name] = {
                        "step": f"Wait {seconds}s",
                        "status": "RUNNING",
                        "timestamp": timestamp_dt,
                        "details": f"Waiting {seconds} seconds",
                        "state_name": wait_state_name,
                        "order": len(steps) + len(state_steps),
                    }

        elif event_type == "WaitStateExited":
            wait_details = event.get("waitStateExitedEventDetails", {})
            wait_state_name = wait_details.get("name", "WaitForJob")
            if wait_state_name in state_steps:
                state_steps[wait_state_name]["status"] = "SUCCEEDED"
                state_steps[wait_state_name]["completed_at"] = timestamp_dt

        elif event_type == "ExecutionSucceeded":
            steps.append(
                {
                    "step": "Execution Completed",
                    "status": "SUCCEEDED",
                    "timestamp": timestamp_dt,
                    "details": "All steps completed successfully",
                    "order": 9999,
                }
            )

        elif event_type == "ExecutionFailed":
            failed_details = event.get("executionFailedEventDetails", {})
            error = failed_details.get("error", "Unknown error")
            cause = failed_details.get("cause", "")
            steps.append(
                {
                    "step": "Execution Failed",
                    "status": "FAILED",
                    "timestamp": timestamp_dt,
                    "details": f"Error: {error}",
                    "cause": cause,
                    "order": 9999,
                }
            )

    for step_data in state_steps.values():
        if step_data.get("timestamp") and step_data.get("completed_at"):
            duration = (step_data["completed_at"] - step_data["timestamp"]).total_seconds()
            step_data["duration"] = duration
        elif step_data.get("started_at") and step_data.get("completed_at"):
            duration = (step_data["completed_at"] - step_data["started_at"]).total_seconds()
            step_data["duration"] = duration

        steps.append(step_data)

    steps.sort(key=lambda x: (x.get("order", 0), x.get("timestamp") or datetime.min))

    return steps


def get_pipeline_stats() -> dict[str, int]:
    """Get aggregated statistics for video pipeline, across all campaigns."""
    try:
        runtime_config = get_runtime_config()
        storage = get_s3_storage()

        all_records = query_processed_media(media_type="video", limit=10000)

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


st.title("🎬 Video Pipeline Dashboard")

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

    custom_campaign = st.text_input(
        "Or enter custom campaign",
        value="" if selected_campaign in PREDEFINED_CAMPAIGNS else selected_campaign,
        help="Leave empty to use selected campaign above",
    )

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

    with st.expander("ℹ️ About This Dashboard", expanded=False):
        st.markdown("""
        This dashboard provides manual control and monitoring for a video processing pipeline built as a single-day demonstration of data engineering capabilities. The pipeline ingests Creative Commons videos from public APIs (Wikimedia Commons and Pixabay), enriches them with Amazon Rekognition computer vision, and stores structured metadata.

        **Purpose:** This demo showcases end-to-end pipeline orchestration, serverless compute, and observability patterns. While production pipelines typically handle thousands or millions of files, this implementation uses small batch sizes to:
        - Minimize AWS resource consumption for demonstration purposes
        - Work within public API rate limits and availability constraints
        - Provide clear visibility into each step of the workflow

        **Workflow:** Ingest → Start Rekognition Jobs → Process (wait/poll) → Finalize Results → Index

        **Automated:** Runs weekly on Mondays via EventBridge. Manual triggers available here for testing and demonstration.
        """)

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

st.markdown("### 📋 Recent VIDEO Executions")
recent_executions = get_recent_executions(limit=10)

has_running = False
if recent_executions:
    has_running = any(e["status"] == "RUNNING" for e in recent_executions)
    if has_running:
        st.info("🔄 Execution in progress... Page will auto-refresh")
        time.sleep(5)
        st.rerun()

if recent_executions:
    for exec_item in recent_executions:
        arn = exec_item.get("execution_arn", "")
        if arn:
            exec_id = arn.split(":")[-1]
            exec_item["execution_id"] = exec_id

    df_data = []
    for exec_item in recent_executions:
        status = exec_item["status"]
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

    df = pd.DataFrame(df_data)

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

recent_executions_summary = get_recent_executions(limit=1)
if recent_executions_summary:
    last_exec = recent_executions_summary[0]

    if "execution_id" not in last_exec or not last_exec.get("execution_id"):
        arn = last_exec.get("execution_arn", "")
        if arn:
            exec_id = arn.split(":")[-1]
            last_exec["execution_id"] = exec_id

    status = last_exec["status"]

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

    ingested_videos = last_exec.get("ingested_videos", [])
    ingested_by_source = last_exec.get("ingested_by_source", {})
    processed_videos = last_exec.get("processed_videos", [])

    if ingested_videos or ingested_by_source:
        st.markdown("#### 📥 Videos Received")

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

    st.markdown("#### Step Functions Execution Log")

    execution_arn = last_exec.get("execution_arn", "")
    if execution_arn:
        with st.spinner("Loading execution history..."):
            history = get_execution_history(execution_arn)
            if history:
                steps = parse_execution_history(history)

                try:
                    runtime_config = get_runtime_config()
                    resources = build_aws_resources(aws_config=runtime_config.aws)
                    stepfunctions = resources["stepfunctions"]
                    exec_details = stepfunctions.describe_execution(executionArn=execution_arn)
                    output_data = (
                        json.loads(exec_details.get("output", "{}"))
                        if exec_details.get("output")
                        else {}
                    )

                    # Enrich each step with output data if available
                    for step in steps:
                        state_name = step.get("state_name", "")

                        # Enrich IngestVideo step
                        if state_name == "IngestVideo" and not step.get("output"):
                            step["output"] = {
                                "ingested_count": output_data.get("ingested_count", 0),
                                "source_counts": output_data.get("source_counts", {}),
                                "metadata_by_source": output_data.get("metadata_by_source", {}),
                                "metadata": output_data.get("metadata", []),
                            }

                        # Enrich StartRekognitionJobs step
                        if state_name == "StartRekognitionJobs" and not step.get("output"):
                            rekognition_data = output_data.get("rekognition", {})
                            step["output"] = {
                                "jobs": rekognition_data.get("jobs", []),
                            }

                        # Enrich FinalizeResults step
                        if state_name == "FinalizeResults" and not step.get("output"):
                            finalization_data = output_data.get("finalization", {})
                            step["output"] = {
                                "processed_count": finalization_data.get("processed_count", 0),
                                "results": finalization_data.get("results", []),
                            }

                        # Enrich IndexVideo step
                        if state_name == "IndexVideo" and not step.get("output"):
                            indexing_data = output_data.get("indexing", {})
                            step["output"] = {
                                "indexed_count": indexing_data.get("indexed_count", 0),
                            }
                except Exception as e:
                    st.warning(f"Could not enrich log with execution output: {e}")

                # Display log-style format
                log_container = st.container()
                with log_container:
                    # Use code block style for log appearance
                    log_lines = []

                    for step in steps:
                        step_name = step.get("step", "Unknown Step")
                        step_status = step.get("status", "UNKNOWN")
                        step_timestamp = step.get("timestamp")
                        step_details = step.get("details", "")
                        step_lambda = step.get("lambda", "")
                        step_output = step.get("output", {})
                        step_error = step.get("error", "")
                        step_cause = step.get("cause", "")
                        step_duration = step.get("duration")
                        step_iterations = step.get("iterations", [])

                        # Format timestamp
                        if step_timestamp:
                            time_str = step_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            time_str = "N/A"

                        # Status prefix
                        if step_status == "SUCCEEDED":
                            status_prefix = "[SUCCESS]"
                            status_color = "#00ff00"
                        elif step_status == "FAILED":
                            status_prefix = "[FAILED]"
                            status_color = "#ff4444"
                        elif step_status == "RUNNING":
                            status_prefix = "[RUNNING]"
                            status_color = "#4488ff"
                        else:
                            status_prefix = "[PENDING]"
                            status_color = "#888888"

                        # Clean step name (remove emojis)
                        clean_step_name = step_name
                        # Remove common emoji patterns
                        import re

                        clean_step_name = re.sub(
                            r"[📥🚀🔄⏳🔍❓✅📝❌]", "", clean_step_name
                        ).strip()

                        # Build log line
                        log_line = f"{time_str} {status_prefix} {clean_step_name}"

                        if step_lambda:
                            log_line += f" | Lambda: {step_lambda}"

                        # Add duration if available
                        if step_duration is not None:
                            if step_duration < 1:
                                log_line += f" | Duration: {step_duration * 1000:.0f}ms"
                            else:
                                log_line += f" | Duration: {step_duration:.1f}s"

                        # Add iteration count for Map State
                        if step_iterations:
                            succeeded_count = sum(
                                1 for it in step_iterations if it.get("status") == "SUCCEEDED"
                            )
                            log_line += f" | Iterations: {succeeded_count}/{len(step_iterations)}"

                        log_lines.append(
                            {
                                "line": log_line,
                                "status": step_status,
                                "color": status_color,
                                "details": step_details,
                                "output": step_output,
                                "error": step_error,
                                "cause": step_cause,
                            }
                        )

                    # Build complete log text with detailed information
                    log_text_lines = []

                    for log_entry in log_lines:
                        log_line = log_entry["line"]
                        log_text_lines.append(log_line)

                        # Show details if available
                        if log_entry["details"]:
                            # Skip generic state details
                            if (
                                not log_entry["details"].startswith("State:")
                                or "Map State" in log_entry["details"]
                            ):
                                log_text_lines.append(f"  → {log_entry['details']}")

                        # Show detailed output information
                        if log_entry["output"] and isinstance(log_entry["output"], dict):
                            output = log_entry["output"]

                            # Ingest step details
                            if "ingested_count" in output:
                                log_text_lines.append(
                                    f"  → Videos Ingested: {output.get('ingested_count', 0)}"
                                )
                                if "source_counts" in output:
                                    source_counts = output.get("source_counts", {})
                                    log_text_lines.append(f"  → By Source: {source_counts}")
                                if "metadata_by_source" in output:
                                    metadata_by_source = output.get("metadata_by_source", {})
                                    for source, videos in metadata_by_source.items():
                                        if videos:
                                            log_text_lines.append(
                                                f"  → {source.capitalize()} Videos:"
                                            )
                                            for video in videos:
                                                video_title = video.get("title", "Untitled")
                                                source_id = video.get("source_id", "")
                                                s3_key = video.get("s3_key", "")
                                                log_text_lines.append(f"    • {video_title}")
                                                log_text_lines.append(f"      ID: {source_id}")
                                                log_text_lines.append(f"      S3 Key: {s3_key}")

                            if "jobs" in output:
                                jobs = output.get("jobs", [])
                                jobs_count = len(jobs)
                                log_text_lines.append(f"  → Rekognition Jobs Started: {jobs_count}")
                                for idx, job in enumerate(jobs, 1):
                                    job_id = job.get("job_id", "N/A")
                                    video_key = job.get("video_s3_key", "N/A")
                                    job_status = job.get("status", "N/A")
                                    log_text_lines.append(f"    Job #{idx}:")
                                    log_text_lines.append(f"      Job ID: {job_id}")
                                    log_text_lines.append(f"      Video: {video_key}")
                                    log_text_lines.append(f"      Status: {job_status}")

                            if "processed_count" in output:
                                log_text_lines.append(
                                    f"  → Videos Processed: {output.get('processed_count', 0)}"
                                )
                                if "results" in output:
                                    results = output.get("results", [])
                                    for idx, result in enumerate(results, 1):
                                        job_id = result.get("job_id", "N/A")
                                        video_key = result.get("video_s3_key", "N/A")
                                        processed_key = result.get("processed_key", "N/A")
                                        summary = result.get("summary", {})
                                        log_text_lines.append(f"    Result #{idx}:")
                                        log_text_lines.append(f"      Job ID: {job_id}")
                                        log_text_lines.append(f"      Video: {video_key}")
                                        log_text_lines.append(f"      Processed: {processed_key}")
                                        if summary:
                                            total_labels = summary.get("total_labels", 0)
                                            top_labels = summary.get("top_labels", [])
                                            log_text_lines.append(
                                                f"      Labels Detected: {total_labels}"
                                            )
                                            if top_labels:
                                                # Extract label names (top_labels is a list of dicts)
                                                label_names = [
                                                    label.get("name", "Unknown")
                                                    for label in top_labels[:5]
                                                    if isinstance(label, dict)
                                                ]
                                                if label_names:
                                                    log_text_lines.append(
                                                        f"      Top Labels: {', '.join(label_names)}"
                                                    )

                            if "indexed_count" in output:
                                log_text_lines.append(
                                    f"  → Videos Indexed: {output.get('indexed_count', 0)}"
                                )

                        if log_entry["status"] == "FAILED":
                            if log_entry["error"]:
                                log_text_lines.append(f"  ERROR: {log_entry['error']}")
                            if log_entry["cause"]:
                                log_text_lines.append(f"  CAUSE: {log_entry['cause']}")

                    # Display as code block with scrollable container
                    log_text = "\n".join(log_text_lines)

                    # Create scrollable container with fixed height
                    st.markdown(
                        """
                    <style>
                    .log-scroll-container {
                        max-height: 600px;
                        overflow-y: auto;
                        overflow-x: auto;
                        border: 1px solid rgba(250, 250, 250, 0.2);
                        border-radius: 5px;
                        padding: 15px;
                        background-color: #0e1117;
                        font-family: 'Courier New', monospace;
                    }
                    .log-scroll-container pre {
                        margin: 0;
                        padding: 0;
                        background: transparent;
                        border: none;
                    }
                    </style>
                    """,
                        unsafe_allow_html=True,
                    )

                    # Display log in scrollable container
                    st.markdown('<div class="log-scroll-container">', unsafe_allow_html=True)
                    st.code(log_text, language="log")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Execution history not available yet. The execution may still be running.")

    # Show execution details in expander
    with st.expander("📋 Execution Metadata", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Time:**", last_exec["timestamp"])
            st.write("**Execution ID:**", last_exec.get("execution_id", "N/A"))
            st.write(
                "**Execution ARN:**",
                execution_arn[:80] + "..." if len(execution_arn) > 80 else execution_arn,
            )
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
