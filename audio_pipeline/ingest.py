"""Audio ingestion from Freesound API."""

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

FREESOUND_API_BASE = "https://freesound.org/apiv2"
CC_LICENSE_FILTER = "license:(cc0 OR cc-by OR cc-by-sa)"


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    """Metadata for an ingested audio file."""

    freesound_id: int
    title: str
    author: str
    license: str
    url: str
    duration: float
    file_size: int
    tags: list[str]
    s3_key: str
    ingested_at: str


class FreesoundClient:
    """Client for Freesound API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {api_key}"})

    def search(
        self,
        query: str,
        *,
        page_size: int = 5,
        fields: str = "id,name,username,license,url,duration,filesize,tags",
    ) -> list[dict[str, Any]]:
        """Search for Creative Commons audio files."""
        params = {
            "query": f"{query} {CC_LICENSE_FILTER}",
            "page_size": page_size,
            "fields": fields,
            "filter": "duration:[0.5 TO 60]",
        }
        response = self.session.get(f"{FREESOUND_API_BASE}/search/text/", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

    def download_preview(self, sound_id: int) -> bytes:
        """Download preview audio file."""
        response = self.session.get(
            f"{FREESOUND_API_BASE}/sounds/{sound_id}/download/",
            timeout=60,
        )
        response.raise_for_status()
        return response.content


def ingest_audio_batch(
    *,
    campaign: str,
    batch_size: int,
    freesound_api_key: str,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> list[AudioMetadata]:
    """Ingest a batch of Creative Commons audio files from Freesound."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    storage = S3Storage(s3_client)
    client = FreesoundClient(freesound_api_key)

    LOGGER.info("Searching Freesound for campaign: %s (batch_size=%d)", campaign, batch_size)
    results = client.search(campaign, page_size=batch_size)

    if not results:
        LOGGER.warning("No results found for campaign: %s", campaign)
        return []

    metadata_list = []
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    for sound in results:
        sound_id = sound["id"]
        LOGGER.info("Downloading sound ID: %d", sound_id)

        try:
            audio_data = invoke_with_retry(
                lambda: client.download_preview(sound_id),
                max_attempts=3,
            )

            s3_key = f"media-raw/audio/{campaign}/{timestamp}/{sound_id}.mp3"
            metadata_dict = {
                "freesound_id": str(sound_id),
                "title": sound.get("name", ""),
                "author": sound.get("username", ""),
                "license": sound.get("license", ""),
            }

            storage.upload_bytes(
                bucket=aws_config.audio_bucket,
                key=s3_key,
                data=audio_data,
                content_type="audio/mpeg",
                metadata=metadata_dict,
            )

            metadata = AudioMetadata(
                freesound_id=sound_id,
                title=sound.get("name", ""),
                author=sound.get("username", ""),
                license=sound.get("license", ""),
                url=sound.get("url", ""),
                duration=sound.get("duration", 0.0),
                file_size=sound.get("filesize", 0),
                tags=sound.get("tags", []),
                s3_key=s3_key,
                ingested_at=timestamp,
            )
            metadata_list.append(metadata)

        except Exception as e:
            LOGGER.error("Failed to ingest sound ID %d: %s", sound_id, e, exc_info=True)
            continue

    LOGGER.info("Ingested %d audio files for campaign: %s", len(metadata_list), campaign)
    return metadata_list
