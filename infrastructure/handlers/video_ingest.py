"""Lambda handler for video ingestion."""

from __future__ import annotations

import logging
import os

from shared.config import get_runtime_config
from video_pipeline.ingest import ingest_video_batch

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """Lambda handler for video ingestion.

    By default, ingests from both Wikimedia Commons and Pixabay simultaneously.
    To use a single source, set 'video_source' in the event to 'wikimedia' or 'pixabay'.
    """
    try:
        # Extract parameters from event
        campaign = event.get("campaign", "default")
        batch_size = int(event.get("batch_size_video", 2))
        # If video_source is not specified, None will use both sources by default
        source = event.get(
            "video_source"
        )  # None = both sources, "wikimedia" or "pixabay" = single source
        pixabay_api_key = event.get("pixabay_api_key") or os.environ.get(
            "MEDIA_PIPELINES_PIXABAY_API_KEY"
        )

        # Get AWS configuration
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

        source_description = source if source else "both (wikimedia + pixabay)"
        LOGGER.info(
            "Starting video ingestion: campaign=%s, batch_size=%d, source=%s",
            campaign,
            batch_size,
            source_description,
        )

        # Ingest video batch (from both sources by default)
        # Returns dict separated by source following data engineering best practices
        results_by_source = ingest_video_batch(
            campaign=campaign,
            batch_size=batch_size,
            source=source,  # None = both sources
            pixabay_api_key=pixabay_api_key,
            aws_config=aws_config,
        )

        # Count videos by source
        source_counts = {
            source_name: len(metadata_list)
            for source_name, metadata_list in results_by_source.items()
        }
        total_ingested = sum(source_counts.values())

        # Convert VideoMetadata objects to dicts for JSON serialization
        # Following data engineering best practices: keep sources separated
        def metadata_to_dict(m):
            """Convert VideoMetadata to dict."""
            return {
                "source": m.source,
                "title": m.title,
                "source_id": m.source_id,
                "file_url": m.file_url,
                "license": m.license,
                "author": m.author,
                "description": m.description,
                "duration": m.duration,
                "file_size": m.file_size,
                "s3_key": m.s3_key,
                "ingested_at": m.ingested_at,
            }

        # Keep metadata separated by source (data engineering best practice)
        metadata_by_source_dict = {
            source_name: [metadata_to_dict(m) for m in metadata_list]
            for source_name, metadata_list in results_by_source.items()
        }

        # Flatten metadata for backward compatibility with downstream steps
        all_metadata = []
        for metadata_list in metadata_by_source_dict.values():
            all_metadata.extend(metadata_list)

        # Prepare output for Step Functions
        # Keep source separation visible in the response structure
        result = {
            "campaign": campaign,
            "batch_size": batch_size,
            "video_source": source_description,
            "ingested_count": total_ingested,
            "source_counts": source_counts,  # e.g., {"wikimedia": 5, "pixabay": 5}
            # Metadata separated by source for better traceability (data engineering best practice)
            "metadata_by_source": metadata_by_source_dict,  # {"wikimedia": [...], "pixabay": [...]}
            # Flattened metadata for backward compatibility with downstream steps
            "metadata": all_metadata,
        }

        LOGGER.info(
            "Video ingestion completed: %d files ingested from %s (counts: %s) - "
            "Results kept separated by source per data engineering best practices",
            total_ingested,
            source_description,
            source_counts,
        )
        return result

    except Exception as e:
        LOGGER.error("Video ingestion failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "campaign": event.get("campaign", "unknown"),
            "ingested_count": 0,
            "metadata": [],
        }
