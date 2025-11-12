"""Lambda handler for starting Rekognition Video jobs."""

from __future__ import annotations

import logging

from shared.config import get_runtime_config
from video_pipeline.rekognition import start_label_detection_job

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for starting Rekognition jobs."""
    try:
        metadata_list = event.get("metadata", [])

        if not metadata_list:
            LOGGER.warning("No metadata provided for Rekognition")
            return {
                "jobs": [],
            }

        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        LOGGER.info(
            "Starting Rekognition jobs for %d videos",
            len(metadata_list),
        )

        jobs = []
        for metadata in metadata_list:
            s3_key = metadata.get("s3_key", "")
            if not s3_key:
                LOGGER.warning("Missing s3_key in metadata, skipping")
                continue

            try:
                job = start_label_detection_job(
                    video_s3_bucket=aws_config.video_bucket,
                    video_s3_key=s3_key,
                    aws_config=aws_config,
                )

                jobs.append(
                    {
                        "job_id": job.job_id,
                        "status": job.status,
                        "video_s3_key": job.video_s3_key,
                        "video_s3_bucket": job.video_s3_bucket,
                    }
                )

            except Exception as e:
                LOGGER.error(
                    "Failed to start Rekognition job for %s: %s",
                    s3_key,
                    e,
                    exc_info=True,
                )
                continue

        LOGGER.info("Started %d Rekognition jobs", len(jobs))
        return {
            "jobs": jobs,
            "campaign": event.get("campaign", "unknown"),
        }

    except Exception as e:
        LOGGER.error("Rekognition job start failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "jobs": [],
            "campaign": event.get("campaign", "unknown"),
        }
