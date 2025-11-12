"""Lambda handler for checking Rekognition Video job status."""

from __future__ import annotations

import logging

from shared.config import get_runtime_config
from video_pipeline.rekognition import get_job_status

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for checking Rekognition job status."""
    try:
        job_id = event.get("job_id", "")

        if not job_id:
            raise ValueError("job_id is required")

        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        LOGGER.info("Checking status for Rekognition job: %s", job_id)

        status = get_job_status(
            job_id=job_id,
            aws_config=aws_config,
        )

        LOGGER.info(
            "Job %s status: %s",
            job_id,
            status.get("JobStatus", "UNKNOWN"),
        )

        return status

    except Exception as e:
        LOGGER.error("Failed to check job status: %s", e, exc_info=True)
        return {
            "JobStatus": "FAILED",
            "StatusMessage": str(e),
            "VideoMetadata": {},
            "Labels": [],
        }
