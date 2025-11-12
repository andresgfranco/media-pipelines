"""Video ingestion from multiple sources (Wikimedia Commons, Pixabay)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

import requests
from botocore.client import BaseClient

from shared.aws import S3Storage, invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)

WIKIMEDIA_API_BASE = "https://commons.wikimedia.org/w/api.php"
PIXABAY_API_BASE = "https://pixabay.com/api/videos/"
CC_LICENSE_CATEGORIES = [
    "Category:CC-BY-4.0",
    "Category:CC-BY-SA-4.0",
    "Category:CC0",
]


class VideoSource(str, Enum):
    """Video source provider."""

    WIKIMEDIA = "wikimedia"
    PIXABAY = "pixabay"


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Metadata for an ingested video file."""

    source: str  # "wikimedia" or "pixabay"
    title: str
    file_url: str
    license: str
    author: str
    description: str
    duration: float | None
    file_size: int
    s3_key: str
    ingested_at: str
    source_id: str | None = None


class VideoSourceClient(Protocol):
    """Protocol for video source clients."""

    def search_videos(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search for Creative Commons video files."""
        ...

    def download_video(self, url: str) -> bytes:
        """Download video file from URL."""
        ...


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
            "gsrnamespace": 6,
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
                categories = page_data.get("categories", [])
                has_cc_license = any(
                    cat.get("title", "").startswith("Category:CC") for cat in categories
                )

                if has_cc_license:
                    extmetadata = imageinfo.get("extmetadata", {})
                    results.append(
                        {
                            "source": "wikimedia",
                            "source_id": page_data.get("title", ""),
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


class PixabayClient:
    """Client for Pixabay API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "MediaPipelines/1.0 (https://github.com/andresgfranco/media-pipelines)"}
        )

    def search_videos(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for Creative Commons video files on Pixabay."""
        params = {
            "key": self.api_key,
            "q": query,
            "video_type": "all",
            "category": "all",
            "min_width": 640,
            "safesearch": "true",
            "per_page": max(min(limit, 20), 3),
            "order": "popular",
        }

        response = self.session.get(PIXABAY_API_BASE, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "hits" not in data:
            return []

        results = []
        for hit in data.get("hits", [])[:limit]:
            video_info = hit.get("videos", {})
            video_url = None
            video_size = 0
            mime_type = "video/mp4"

            if "medium" in video_info:
                video_url = video_info["medium"].get("url", "")
                video_size = video_info["medium"].get("size", 0)
            elif "small" in video_info:
                video_url = video_info["small"].get("url", "")
                video_size = video_info["small"].get("size", 0)
            elif "large" in video_info:
                video_url = video_info["large"].get("url", "")
                video_size = video_info["large"].get("size", 0)

            if not video_url:
                continue

            results.append(
                {
                    "source": "pixabay",
                    "source_id": str(hit.get("id", "")),
                    "title": hit.get("tags", query),
                    "url": video_url,
                    "size": video_size,
                    "mime": mime_type,
                    "author": hit.get("user", ""),
                    "license": "Pixabay License (Free for commercial use)",
                    "description": hit.get("tags", ""),
                    "duration": hit.get("duration", 0),
                }
            )

        return results

    def download_video(self, url: str) -> bytes:
        """Download video file from URL."""
        response = self.session.get(url, timeout=120, stream=True)
        response.raise_for_status()
        return response.content


def _create_video_client(
    source: VideoSource, pixabay_api_key: str | None = None
) -> VideoSourceClient:
    """Create a video source client based on the source type."""
    if source == VideoSource.PIXABAY:
        if not pixabay_api_key:
            raise ValueError("Pixabay API key is required when using Pixabay source")
        return PixabayClient(api_key=pixabay_api_key)
    elif source == VideoSource.WIKIMEDIA:
        return WikimediaCommonsClient()
    else:
        raise ValueError(f"Unknown video source: {source}")


def _ingest_from_source(
    *,
    campaign: str,
    batch_size: int,
    source: VideoSource,
    pixabay_api_key: str | None,
    s3_client: BaseClient,
    aws_config: AwsConfig,
    timestamp: str,
) -> list[VideoMetadata]:
    """Ingest videos from a single source.

    Args:
        campaign: Search query/campaign name
        batch_size: Number of videos to ingest from this source
        source: Video source provider
        pixabay_api_key: API key for Pixabay (if needed)
        s3_client: S3 client
        aws_config: AWS configuration
        timestamp: Timestamp for this batch

    Returns:
        List of VideoMetadata objects from this source
    """
    try:
        client = _create_video_client(source, pixabay_api_key)
        storage = S3Storage(s3_client)
        source_name = source.value

        LOGGER.info(
            "Searching %s for campaign: %s (batch_size=%d)",
            source_name,
            campaign,
            batch_size,
        )
        results = client.search_videos(campaign, limit=batch_size)

        if not results:
            LOGGER.warning("No results found for campaign: %s on %s", campaign, source_name)
            return []

        metadata_list = []

        from shared.index import query_processed_media

        existing_videos = query_processed_media(
            media_type="video",
            campaign=campaign,
            aws_config=aws_config,
        )
        existing_source_ids = {
            record.metadata.get("source_id", "")
            for record in existing_videos
            if record.metadata.get("source") == source_name
        }

        for video in results:
            video_url = video["url"]
            video_title = video.get("title", "untitled")
            video_source = video.get("source", source_name)
            source_id = video.get("source_id")

            if source_id and source_id in existing_source_ids:
                LOGGER.info(
                    "Skipping duplicate video from %s: %s (source_id: %s)",
                    video_source,
                    video_title,
                    source_id,
                )
                continue

            LOGGER.info("Downloading video from %s: %s", video_source, video_title)

            try:
                video_data = invoke_with_retry(
                    lambda: client.download_video(video_url),
                    max_attempts=3,
                )

                mime_type = video.get("mime", "video/mp4")
                if "mp4" in mime_type or "mp4" in video_url:
                    ext = "mp4"
                elif "webm" in mime_type or "webm" in video_url:
                    ext = "webm"
                else:
                    ext = "mp4"

                safe_title = video_title.replace("File:", "").replace(" ", "_")
                safe_title = "".join(c for c in safe_title if c.isalnum() or c in ("_", "-", "."))[
                    :100
                ]
                if source_id:
                    file_name = f"{video_source}_{source_id}_{safe_title}"
                else:
                    file_name = f"{video_source}_{safe_title}"

                s3_key = f"media-raw/video/{video_source}/{campaign}/{timestamp}/{file_name}.{ext}"

                metadata_dict = {
                    "source": video_source,
                    "title": video_title,
                    "source_id": source_id or "",
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
                    source=video_source,
                    title=video_title,
                    file_url=video_url,
                    license=video.get("license", ""),
                    author=video.get("author", ""),
                    description=video.get("description", ""),
                    duration=video.get("duration"),
                    file_size=video.get("size", len(video_data)),
                    s3_key=s3_key,
                    ingested_at=timestamp,
                    source_id=source_id,
                )
                metadata_list.append(metadata)

            except Exception as e:
                LOGGER.error(
                    "Failed to ingest video %s from %s: %s",
                    video_title,
                    video_source,
                    e,
                    exc_info=True,
                )
                continue

        LOGGER.info(
            "Ingested %d video files from %s for campaign: %s",
            len(metadata_list),
            source_name,
            campaign,
        )
        return metadata_list

    except Exception as e:
        LOGGER.error(
            "Failed to ingest from source %s: %s",
            source.value,
            e,
            exc_info=True,
        )
        return []


def ingest_video_batch(
    *,
    campaign: str,
    batch_size: int,
    source: VideoSource | str | None = None,
    pixabay_api_key: str | None = None,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> dict[str, list[VideoMetadata]]:
    """Ingest a batch of Creative Commons video files from multiple sources.

    By default, ingests from both Wikimedia Commons and Pixabay simultaneously.
    The batch_size is distributed evenly between sources (e.g., batch_size=10 = 5 from each).

    Results are kept separated by source for traceability, compliance, and independent analysis.

    Args:
        campaign: Search query/campaign name
        batch_size: Total number of videos to ingest (distributed across sources)
        source: Optional video source provider ("wikimedia", "pixabay", or None for both)
        pixabay_api_key: API key for Pixabay (will try env var if not provided)
        s3_client: Optional S3 client
        aws_config: Optional AWS configuration

    Returns:
        Dictionary with source as key and list of VideoMetadata as value.
        Example: {"wikimedia": [...], "pixabay": [...]}
    """
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    # Determine which sources to use
    sources_to_use: list[VideoSource] = []
    if source is None:
        # Default: use both sources
        sources_to_use = [VideoSource.WIKIMEDIA, VideoSource.PIXABAY]
    else:
        if isinstance(source, str):
            try:
                sources_to_use = [VideoSource(source.lower())]
            except ValueError:
                LOGGER.warning("Unknown source '%s', using both sources", source)
                sources_to_use = [VideoSource.WIKIMEDIA, VideoSource.PIXABAY]
        else:
            sources_to_use = [source]

    if VideoSource.PIXABAY in sources_to_use and not pixabay_api_key:
        import os

        pixabay_api_key = os.environ.get("MEDIA_PIPELINES_PIXABAY_API_KEY")
        if not pixabay_api_key:
            LOGGER.warning(
                "Pixabay API key not found. Skipping Pixabay source. "
                "Set MEDIA_PIPELINES_PIXABAY_API_KEY environment variable to enable Pixabay."
            )
            sources_to_use = [s for s in sources_to_use if s != VideoSource.PIXABAY]

    if not sources_to_use:
        LOGGER.error("No valid sources available for video ingestion")
        return {}

    videos_per_source = max(1, batch_size // len(sources_to_use))
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    LOGGER.info(
        "Ingesting videos from %d source(s) for campaign: %s (total batch_size=%d, ~%d per source)",
        len(sources_to_use),
        campaign,
        batch_size,
        videos_per_source,
    )

    results_by_source: dict[str, list[VideoMetadata]] = {}

    for source in sources_to_use:
        source_name = source.value
        source_metadata = _ingest_from_source(
            campaign=campaign,
            batch_size=videos_per_source,
            source=source,
            pixabay_api_key=pixabay_api_key if source == VideoSource.PIXABAY else None,
            s3_client=s3_client,
            aws_config=aws_config,
            timestamp=timestamp,
        )
        results_by_source[source_name] = source_metadata

    total_ingested = sum(len(metadata) for metadata in results_by_source.values())
    LOGGER.info(
        "Total ingested: %d video files for campaign: %s from %d source(s)",
        total_ingested,
        campaign,
        len(sources_to_use),
    )

    return results_by_source
