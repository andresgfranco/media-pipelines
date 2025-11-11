"""Video ingestion from Wikimedia Commons API."""

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

WIKIMEDIA_API_BASE = "https://commons.wikimedia.org/w/api.php"
CC_LICENSE_CATEGORIES = [
    "Category:CC-BY-4.0",
    "Category:CC-BY-SA-4.0",
    "Category:CC0",
]


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Metadata for an ingested video file."""

    wikimedia_title: str
    file_url: str
    license: str
    author: str
    description: str
    duration: float | None
    file_size: int
    s3_key: str
    ingested_at: str


class WikimediaCommonsClient:
    """Client for Wikimedia Commons API."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "MediaPipelines/1.0 (https://github.com/andresgfranco/media-pipelines)"}
        )

    def search_videos(
        self,
        query: str,
        *,
        limit: int = 5,
        file_type: str = "video",
    ) -> list[dict[str, Any]]:
        """Search for Creative Commons video files."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:{file_type}",
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": limit,
            "prop": "imageinfo|categories",
            "iiprop": "url|size|extmetadata",
            "clcategories": "|".join(CC_LICENSE_CATEGORIES),
            "cllimit": 50,
        }

        response = self.session.get(WIKIMEDIA_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "query" not in data or "pages" not in data["query"]:
            return []

        results = []
        for page_id, page_data in data["query"]["pages"].items():
            if "imageinfo" not in page_data or not page_data["imageinfo"]:
                continue

            imageinfo = page_data["imageinfo"][0]
            if imageinfo.get("mime", "").startswith("video/"):
                # Check if it has CC license category
                categories = page_data.get("categories", [])
                has_cc_license = any(
                    cat.get("title", "").startswith("Category:CC") for cat in categories
                )

                if has_cc_license:
                    extmetadata = imageinfo.get("extmetadata", {})
                    results.append(
                        {
                            "title": page_data.get("title", ""),
                            "url": imageinfo.get("url", ""),
                            "size": imageinfo.get("size", 0),
                            "mime": imageinfo.get("mime", ""),
                            "author": extmetadata.get("Artist", {}).get("value", ""),
                            "license": extmetadata.get("License", {}).get("value", ""),
                            "description": extmetadata.get("ImageDescription", {}).get("value", ""),
                        }
                    )

        return results[:limit]

    def download_video(self, url: str) -> bytes:
        """Download video file from URL."""
        response = self.session.get(url, timeout=120, stream=True)
        response.raise_for_status()
        return response.content


def ingest_video_batch(
    *,
    campaign: str,
    batch_size: int,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> list[VideoMetadata]:
    """Ingest a batch of Creative Commons video files from Wikimedia Commons."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    client = WikimediaCommonsClient()
    storage = S3Storage(s3_client)

    LOGGER.info(
        "Searching Wikimedia Commons for campaign: %s (batch_size=%d)",
        campaign,
        batch_size,
    )
    results = client.search_videos(campaign, limit=batch_size)

    if not results:
        LOGGER.warning("No results found for campaign: %s", campaign)
        return []

    metadata_list = []
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    for video in results:
        video_url = video["url"]
        video_title = video["title"]
        LOGGER.info("Downloading video: %s", video_title)

        try:
            video_data = invoke_with_retry(
                lambda: client.download_video(video_url),
                max_attempts=3,
            )

            # Extract file extension from MIME type or URL
            mime_type = video.get("mime", "video/mp4")
            ext = "mp4" if "mp4" in mime_type else "webm"
            file_name = video_title.replace("File:", "").replace(" ", "_")
            s3_key = f"media-raw/video/{campaign}/{timestamp}/{file_name}.{ext}"

            metadata_dict = {
                "wikimedia_title": video_title,
                "license": video.get("license", ""),
                "author": video.get("author", ""),
            }

            storage.upload_bytes(
                bucket=aws_config.video_bucket,
                key=s3_key,
                data=video_data,
                content_type=mime_type,
                metadata=metadata_dict,
            )

            metadata = VideoMetadata(
                wikimedia_title=video_title,
                file_url=video_url,
                license=video.get("license", ""),
                author=video.get("author", ""),
                description=video.get("description", ""),
                duration=None,  # Would need to extract from video file
                file_size=video.get("size", len(video_data)),
                s3_key=s3_key,
                ingested_at=timestamp,
            )
            metadata_list.append(metadata)

        except Exception as e:
            LOGGER.error("Failed to ingest video %s: %s", video_title, e, exc_info=True)
            continue

    LOGGER.info("Ingested %d video files for campaign: %s", len(metadata_list), campaign)
    return metadata_list
