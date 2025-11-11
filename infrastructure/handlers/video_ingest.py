"""Lambda handler for video ingestion."""

from __future__ import annotations

import logging

from shared.config import get_runtime_config
from video_pipeline.ingest import ingest_video_batch

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for video ingestion."""
    try:
        # Extract parameters from event
        campaign = event.get("campaign", "default")
        batch_size = int(event.get("batch_size_video", 2))

        # Get AWS configuration
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        LOGGER.info(
            "Starting video ingestion: campaign=%s, batch_size=%d",
            campaign,
            batch_size,
        )

        # Ingest video batch
        metadata_list = ingest_video_batch(
            campaign=campaign,
            batch_size=batch_size,
            aws_config=aws_config,
        )

        # Prepare output for Step Functions
        result = {
            "campaign": campaign,
            "batch_size": batch_size,
            "ingested_count": len(metadata_list),
            "metadata": [
                {
                    "wikimedia_title": m.wikimedia_title,
                    "file_url": m.file_url,
                    "license": m.license,
                    "author": m.author,
                    "description": m.description,
                    "duration": m.duration,
                    "file_size": m.file_size,
                    "s3_key": m.s3_key,
                    "ingested_at": m.ingested_at,
                }
                for m in metadata_list
            ],
        }

        LOGGER.info("Video ingestion completed: %d files ingested", len(metadata_list))
        return result

    except Exception as e:
        LOGGER.error("Video ingestion failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "campaign": event.get("campaign", "unknown"),
            "ingested_count": 0,
            "metadata": [],
        }
