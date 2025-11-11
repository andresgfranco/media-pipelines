"""Lambda handler for indexing processed video files."""

from __future__ import annotations

import logging

from shared.config import get_runtime_config
from shared.index import index_processed_media

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for indexing processed video."""
    try:
        # Extract parameters from event (from finalization step)
        campaign = event.get("campaign", "unknown")
        results = event.get("finalization", {}).get("results", [])

        if not results:
            LOGGER.warning("No results to index")
            return {"indexed_count": 0}

        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        indexed_count = 0
        for result in results:
            video_s3_key = result.get("video_s3_key", "")
            processed_key = result.get("processed_key", "")
            summary = result.get("summary", {})

            if not video_s3_key or not processed_key:
                continue

            # Extract ingested_at from s3_key path
            parts = video_s3_key.split("/")
            ingested_at = parts[-2] if len(parts) >= 2 else ""

            try:
                index_processed_media(
                    media_type="video",
                    campaign=campaign,
                    s3_key=video_s3_key,
                    processed_key=processed_key,
                    ingested_at=ingested_at,
                    metadata=summary,
                    aws_config=aws_config,
                )
                indexed_count += 1
            except Exception as e:
                LOGGER.error("Failed to index video file %s: %s", video_s3_key, e, exc_info=True)
                continue

        LOGGER.info("Indexed %d video files", indexed_count)
        return {"indexed_count": indexed_count, "campaign": campaign}

    except Exception as e:
        LOGGER.error("Video indexing failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "indexed_count": 0,
            "campaign": event.get("campaign", "unknown"),
        }
