"""Lambda handler for finalizing Rekognition Video results."""

from __future__ import annotations

import logging

from shared.config import get_runtime_config
from video_pipeline.finalize import finalize_video_analysis, save_analysis_to_s3

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for finalizing Rekognition results."""
    try:
        # Extract parameters from event (from wait step)
        jobs = event.get("jobs", [])

        if not jobs:
            LOGGER.warning("No jobs provided for finalization")
            return {
                "campaign": event.get("campaign", "unknown"),
                "processed_count": 0,
                "results": [],
            }

        # Get AWS configuration
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        LOGGER.info("Finalizing Rekognition results for %d jobs", len(jobs))

        results = []
        for job_data in jobs:
            job_id = job_data.get("job_id", "")
            video_s3_key = job_data.get("video_s3_key", "")

            if not job_id or not video_s3_key:
                LOGGER.warning("Missing job_id or video_s3_key, skipping")
                continue

            try:
                # Finalize analysis
                analysis = finalize_video_analysis(
                    job_id=job_id,
                    video_s3_key=video_s3_key,
                    aws_config=aws_config,
                )

                # Save to processed bucket
                processed_key = (
                    video_s3_key.replace("media-raw", "media-processed")
                    .replace(".mp4", "_labels.json")
                    .replace(".webm", "_labels.json")
                )

                save_analysis_to_s3(
                    analysis=analysis,
                    bucket=aws_config.video_bucket,
                    key=processed_key,
                    aws_config=aws_config,
                )

                results.append(
                    {
                        "job_id": job_id,
                        "video_s3_key": video_s3_key,
                        "processed_key": processed_key,
                        "summary": analysis.summary,
                    }
                )

            except Exception as e:
                LOGGER.error(
                    "Failed to finalize job %s: %s",
                    job_id,
                    e,
                    exc_info=True,
                )
                continue

        LOGGER.info("Finalized %d Rekognition jobs", len(results))
        return {
            "campaign": event.get("campaign", "unknown"),
            "processed_count": len(results),
            "results": results,
        }

    except Exception as e:
        LOGGER.error("Rekognition finalization failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "campaign": event.get("campaign", "unknown"),
            "processed_count": 0,
            "results": [],
        }
