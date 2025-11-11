"""Lambda handler for audio analysis."""

from __future__ import annotations

import logging

from audio_pipeline.analyze import process_audio_batch
from shared.config import get_runtime_config

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for audio analysis."""
    try:
        # Extract parameters from event (from previous step)
        campaign = event.get("campaign", "default")
        metadata_list = event.get("metadata", [])

        if not metadata_list:
            LOGGER.warning("No metadata provided for analysis")
            return {
                "campaign": campaign,
                "processed_count": 0,
                "results": [],
            }

        # Extract timestamp from first metadata item
        timestamp = metadata_list[0].get("ingested_at", "") if metadata_list else ""

        LOGGER.info(
            "Starting audio analysis: campaign=%s, files=%d",
            campaign,
            len(metadata_list),
        )

        # Get AWS configuration
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        # Process audio batch
        results = process_audio_batch(
            campaign=campaign,
            timestamp=timestamp,
            metadata_list=metadata_list,
            aws_config=aws_config,
        )

        LOGGER.info("Audio analysis completed: %d files processed", len(results))
        return {
            "campaign": campaign,
            "processed_count": len(results),
            "results": results,
        }

    except Exception as e:
        LOGGER.error("Audio analysis failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "campaign": event.get("campaign", "unknown"),
            "processed_count": 0,
            "results": [],
        }
