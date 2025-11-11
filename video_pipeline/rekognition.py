"""Amazon Rekognition Video integration for video analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from botocore.client import BaseClient

from shared.aws import invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RekognitionJob:
    """Rekognition Video job information."""

    job_id: str
    status: str
    video_s3_key: str
    video_s3_bucket: str


def start_label_detection_job(
    *,
    video_s3_bucket: str,
    video_s3_key: str,
    rekognition_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
    notification_channel: dict[str, str] | None = None,
) -> RekognitionJob:
    """Start a Rekognition Video label detection job."""
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

    video_uri = {
        "S3Object": {
            "Bucket": video_s3_bucket,
            "Name": video_s3_key,
        }
    }

    params: dict[str, Any] = {
        "Video": video_uri,
    }

    if notification_channel:
        params["NotificationChannel"] = notification_channel

    def _start_job() -> dict:
        return rekognition_client.start_label_detection(**params)

    LOGGER.info(
        "Starting Rekognition label detection job for: s3://%s/%s",
        video_s3_bucket,
        video_s3_key,
    )

    response = invoke_with_retry(_start_job, max_attempts=3)
    job_id = response["JobId"]

    LOGGER.info("Rekognition job started: %s", job_id)

    return RekognitionJob(
        job_id=job_id,
        status="IN_PROGRESS",
        video_s3_key=video_s3_key,
        video_s3_bucket=video_s3_bucket,
    )


def get_job_status(
    *,
    job_id: str,
    rekognition_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> dict[str, Any]:
    """Get the status of a Rekognition Video job."""
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

    def _get_job_status() -> dict:
        return rekognition_client.get_label_detection(JobId=job_id)

    response = invoke_with_retry(_get_job_status, max_attempts=3)
    return {
        "JobStatus": response.get("JobStatus", "UNKNOWN"),
        "StatusMessage": response.get("StatusMessage", ""),
        "VideoMetadata": response.get("VideoMetadata", {}),
        "Labels": response.get("Labels", []),
    }
