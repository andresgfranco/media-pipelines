"""Finalize and normalize Rekognition Video results."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from botocore.client import BaseClient

from shared.aws import S3Storage, invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VideoLabel:
    """Normalized video label information."""

    name: str
    confidence: float
    timestamp: float | None
    instances: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class VideoAnalysis:
    """Final video analysis results."""

    video_s3_key: str
    duration: float | None
    labels: list[VideoLabel]
    moderation_labels: list[dict[str, Any]]
    summary: dict[str, Any]


def normalize_rekognition_labels(
    rekognition_response: dict[str, Any],
) -> list[VideoLabel]:
    """Normalize Rekognition labels into a consistent format."""
    labels = []
    raw_labels = rekognition_response.get("Labels", [])

    for label_data in raw_labels:
        label = VideoLabel(
            name=label_data.get("Label", {}).get("Name", ""),
            confidence=label_data.get("Label", {}).get("Confidence", 0.0),
            timestamp=label_data.get("Timestamp", 0) / 1000.0
            if label_data.get("Timestamp")
            else None,
            instances=label_data.get("Label", {}).get("Instances", []),
        )
        labels.append(label)

    return labels


def finalize_video_analysis(
    *,
    job_id: str,
    video_s3_key: str,
    rekognition_client: BaseClient | None = None,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> VideoAnalysis:
    """Finalize video analysis by retrieving and normalizing Rekognition results."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if rekognition_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        rekognition_client = resources.get("rekognition")

        if rekognition_client is None:
            from shared.aws import AwsSessionFactory

            factory = AwsSessionFactory(region=aws_config.region)
            rekognition_client = factory.client("rekognition")

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    def _get_results() -> dict:
        return rekognition_client.get_label_detection(JobId=job_id)

    LOGGER.info("Retrieving Rekognition results for job: %s", job_id)
    rekognition_response = invoke_with_retry(_get_results, max_attempts=3)

    if rekognition_response.get("JobStatus") != "SUCCEEDED":
        raise RuntimeError(
            f"Rekognition job {job_id} did not succeed: "
            f"{rekognition_response.get('StatusMessage', 'Unknown error')}"
        )

    video_metadata = rekognition_response.get("VideoMetadata", {})
    duration = (
        video_metadata.get("DurationMillis", 0) / 1000.0
        if video_metadata.get("DurationMillis")
        else None
    )

    labels = normalize_rekognition_labels(rekognition_response)
    moderation_labels = rekognition_response.get("ModerationLabels", [])

    # Create summary
    top_labels = sorted(labels, key=lambda x: x.confidence, reverse=True)[:10]
    summary = {
        "total_labels": len(labels),
        "top_labels": [
            {"name": label.name, "confidence": label.confidence} for label in top_labels
        ],
        "duration": duration,
        "has_moderation_issues": len(moderation_labels) > 0,
    }

    analysis = VideoAnalysis(
        video_s3_key=video_s3_key,
        duration=duration,
        labels=labels,
        moderation_labels=moderation_labels,
        summary=summary,
    )

    return analysis


def save_analysis_to_s3(
    *,
    analysis: VideoAnalysis,
    bucket: str,
    key: str,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> None:
    """Save video analysis results as JSON to S3."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    storage = S3Storage(s3_client)

    # Convert to dict for JSON serialization
    analysis_dict = {
        "video_s3_key": analysis.video_s3_key,
        "duration": analysis.duration,
        "labels": [
            {
                "name": label.name,
                "confidence": label.confidence,
                "timestamp": label.timestamp,
                "instances": label.instances,
            }
            for label in analysis.labels
        ],
        "moderation_labels": analysis.moderation_labels,
        "summary": analysis.summary,
    }

    json_data = json.dumps(analysis_dict, indent=2).encode("utf-8")

    storage.upload_bytes(
        bucket=bucket,
        key=key,
        data=json_data,
        content_type="application/json",
    )

    LOGGER.info("Saved video analysis to s3://%s/%s", bucket, key)
