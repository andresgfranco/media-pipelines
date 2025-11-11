"""Audio ingestion from Internet Archive API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests
from botocore.client import BaseClient

from shared.aws import S3Storage, invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)

INTERNET_ARCHIVE_SEARCH_URL = "https://archive.org/advancedsearch.php"
INTERNET_ARCHIVE_METADATA_URL = "https://archive.org/metadata"
MIN_DURATION_SECONDS = 0.5
MAX_DURATION_SECONDS = 60.0


def _parse_duration(duration_str: str | float | int) -> float:
    """Parse duration string to seconds.

    Handles formats:
    - Numeric string: "5.5" -> 5.5
    - Time format: "00:10" -> 10.0
    - Already numeric: 5.5 -> 5.5
    """
    if isinstance(duration_str, int | float):
        return float(duration_str)

    duration_str = str(duration_str).strip()

    # Try parsing as MM:SS format
    if ":" in duration_str:
        parts = duration_str.split(":")
        if len(parts) == 2:
            try:
                minutes = float(parts[0])
                seconds = float(parts[1])
                return (minutes * 60) + seconds
            except ValueError:
                pass

    # Try parsing as numeric string
    try:
        return float(duration_str)
    except ValueError:
        return 0.0


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    """Metadata for an ingested audio file."""

    archive_id: str
    title: str
    author: str
    license: str
    url: str
    duration: float
    file_size: int
    tags: list[str]
    s3_key: str
    ingested_at: str


class InternetArchiveClient:
    """Client for Internet Archive API."""

    def __init__(self) -> None:
        self.session = requests.Session()

    def search(
        self,
        query: str,
        *,
        rows: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for Creative Commons audio files."""
        search_query = f"title:{query} AND mediatype:audio AND licenseurl:*creativecommons*"
        params = {
            "q": search_query,
            "fl": "identifier,title,creator,date,licenseurl,downloads",
            "output": "json",
            "rows": rows,
        }
        response = self.session.get(INTERNET_ARCHIVE_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("response", {}).get("docs", [])

    def get_metadata(self, identifier: str) -> dict[str, Any]:
        """Get detailed metadata for an item, including file information."""
        url = f"{INTERNET_ARCHIVE_METADATA_URL}/{identifier}"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def download_file(self, identifier: str, filename: str) -> bytes:
        """Download audio file from Internet Archive."""
        url = f"https://archive.org/download/{identifier}/{filename}"
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.content

    def select_audio_file(self, files: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Select the best audio file from available files."""
        # Filter for audio formats
        audio_formats = ["VBR MP3", "64Kbps MP3", "128Kbps MP3", "OGG VORBIS"]
        audio_files = []

        for f in files:
            if f.get("format") not in audio_formats:
                continue

            length_str = f.get("length")
            if not length_str:
                continue

            try:
                duration = _parse_duration(length_str)
                if MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
                    audio_files.append(f)
            except (ValueError, TypeError):
                # Skip files with invalid duration format
                continue

        if not audio_files:
            return None

        # Prefer VBR MP3, then 128Kbps MP3, then others
        preferred_order = ["VBR MP3", "128Kbps MP3", "64Kbps MP3", "OGG VORBIS"]
        for format_type in preferred_order:
            for f in audio_files:
                if f.get("format") == format_type:
                    return f

        # Fallback to first audio file
        return audio_files[0]


def ingest_audio_batch(
    *,
    campaign: str,
    batch_size: int,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> list[AudioMetadata]:
    """Ingest a batch of Creative Commons audio files from Internet Archive."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    storage = S3Storage(s3_client)
    client = InternetArchiveClient()

    LOGGER.info("Searching Internet Archive for campaign: %s (batch_size=%d)", campaign, batch_size)
    results = client.search(campaign, rows=batch_size)

    if not results:
        LOGGER.warning("No results found for campaign: %s", campaign)
        return []

    metadata_list = []
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    for item in results:
        identifier = item.get("identifier")
        if not identifier:
            continue

        LOGGER.info("Processing item: %s", identifier)

        try:
            # Get detailed metadata including files
            item_metadata = invoke_with_retry(
                lambda: client.get_metadata(identifier),
                max_attempts=3,
            )

            files = item_metadata.get("files", [])
            selected_file = client.select_audio_file(files)

            if not selected_file:
                LOGGER.warning(
                    "No suitable audio file found for item: %s (duration or format filter)",
                    identifier,
                )
                continue

            filename = selected_file.get("name")
            duration = _parse_duration(selected_file.get("length", 0))
            file_size = int(selected_file.get("size", 0))

            # Download the file
            LOGGER.info("Downloading file: %s from item: %s", filename, identifier)
            audio_data = invoke_with_retry(
                lambda: client.download_file(identifier, filename),
                max_attempts=3,
            )

            # Determine content type
            content_type = "audio/mpeg"
            if filename.endswith(".ogg"):
                content_type = "audio/ogg"

            s3_key = f"media-raw/audio/{campaign}/{timestamp}/{identifier}_{filename}"
            metadata_dict = {
                "archive_id": identifier,
                "title": item.get("title", ""),
                "author": item.get("creator", "Unknown"),
                "license": item.get("licenseurl", ""),
            }

            storage.upload_bytes(
                bucket=aws_config.audio_bucket,
                key=s3_key,
                data=audio_data,
                content_type=content_type,
                metadata=metadata_dict,
            )

            # Build item URL
            item_url = f"https://archive.org/details/{identifier}"

            metadata = AudioMetadata(
                archive_id=identifier,
                title=item.get("title", ""),
                author=item.get("creator", "Unknown"),
                license=item.get("licenseurl", ""),
                url=item_url,
                duration=duration,
                file_size=file_size,
                tags=[],  # Internet Archive doesn't provide tags in search results
                s3_key=s3_key,
                ingested_at=timestamp,
            )
            metadata_list.append(metadata)

        except Exception as e:
            LOGGER.error("Failed to ingest item %s: %s", identifier, e, exc_info=True)
            continue

    LOGGER.info("Ingested %d audio files for campaign: %s", len(metadata_list), campaign)
    return metadata_list
