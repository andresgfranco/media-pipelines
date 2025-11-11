"""Lambda handler for audio ingestion."""

from __future__ import annotations

import logging

from audio_pipeline.ingest import ingest_audio_batch
from shared.config import get_runtime_config

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for audio ingestion."""
    try:
        # Extract parameters from event
        campaign = event.get("campaign", "default")
        batch_size = int(event.get("batch_size_audio", 5))

        # Get AWS configuration
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        LOGGER.info(
            "Starting audio ingestion: campaign=%s, batch_size=%d",
            campaign,
            batch_size,
        )

        # Ingest audio batch (no API key needed for Internet Archive)
        metadata_list = ingest_audio_batch(
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
                    "archive_id": m.archive_id,
                    "title": m.title,
                    "author": m.author,
                    "license": m.license,
                    "url": m.url,
                    "duration": m.duration,
                    "file_size": m.file_size,
                    "tags": m.tags,
                    "s3_key": m.s3_key,
                    "ingested_at": m.ingested_at,
                }
                for m in metadata_list
            ],
        }

        LOGGER.info("Audio ingestion completed: %d files ingested", len(metadata_list))
        return result

    except Exception as e:
        LOGGER.error("Audio ingestion failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "campaign": event.get("campaign", "unknown"),
            "ingested_count": 0,
            "metadata": [],
        }
