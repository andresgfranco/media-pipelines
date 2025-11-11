"""Tests for video ingestion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.client import BaseClient

from shared.config import AwsConfig
from video_pipeline.ingest import (
    VideoMetadata,
    WikimediaCommonsClient,
    ingest_video_batch,
)


@pytest.fixture
def mock_wikimedia_response():
    """Mock Wikimedia Commons API search response."""
    return {
        "query": {
            "pages": {
                "12345": {
                    "title": "File:Test_Video.mp4",
                    "imageinfo": [
                        {
                            "url": "https://commons.wikimedia.org/wiki/File:Test_Video.mp4",
                            "size": 1024000,
                            "mime": "video/mp4",
                            "extmetadata": {
                                "Artist": {"value": "testuser"},
                                "License": {"value": "CC-BY-4.0"},
                                "ImageDescription": {"value": "Test video"},
                            },
                        }
                    ],
                    "categories": [{"title": "Category:CC-BY-4.0"}],
                },
                "67890": {
                    "title": "File:Another_Video.webm",
                    "imageinfo": [
                        {
                            "url": "https://commons.wikimedia.org/wiki/File:Another_Video.webm",
                            "size": 512000,
                            "mime": "video/webm",
                            "extmetadata": {
                                "Artist": {"value": "anotheruser"},
                                "License": {"value": "CC0"},
                                "ImageDescription": {"value": "Another video"},
                            },
                        }
                    ],
                    "categories": [{"title": "Category:CC0"}],
                },
            }
        }
    }


@pytest.fixture
def mock_s3_client():
    """Mock S3 client."""
    client = MagicMock(spec=BaseClient)
    client.put_object = MagicMock(return_value={"ETag": "test-etag"})
    return client


@pytest.fixture
def aws_config():
    """Test AWS configuration."""
    return AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )


def test_wikimedia_client_search(mock_wikimedia_response):
    """Test Wikimedia Commons client search."""
    with patch("video_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_wikimedia_response
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = WikimediaCommonsClient()
        results = client.search_videos("nature", limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "File:Test_Video.mp4"
        assert results[0]["mime"] == "video/mp4"
        assert results[1]["title"] == "File:Another_Video.webm"


def test_wikimedia_client_download():
    """Test Wikimedia Commons client download."""
    with patch("video_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.content = b"fake video data"
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = WikimediaCommonsClient()
        data = client.download_video("https://example.com/video.mp4")

        assert data == b"fake video data"


@patch("video_pipeline.ingest.get_runtime_config")
def test_ingest_video_batch(
    mock_get_config,
    mock_wikimedia_response,
    mock_s3_client,
    aws_config,
):
    """Test video batch ingestion."""
    mock_get_config.return_value.aws = aws_config

    with patch("video_pipeline.ingest.WikimediaCommonsClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_videos.return_value = [
            {
                "source": "wikimedia",
                "source_id": "File:Test_Video.mp4",
                "title": "File:Test_Video.mp4",
                "url": "https://example.com/video.mp4",
                "size": 1024000,
                "mime": "video/mp4",
                "author": "testuser",
                "license": "CC-BY-4.0",
                "description": "Test video",
            }
        ]
        mock_client.download_video.return_value = b"fake video data"
        mock_client_class.return_value = mock_client

        # ingest_video_batch now returns dict separated by source
        results_by_source = ingest_video_batch(
            campaign="nature",
            batch_size=1,
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        assert "wikimedia" in results_by_source
        assert len(results_by_source["wikimedia"]) == 1
        metadata = results_by_source["wikimedia"][0]
        assert metadata.title == "File:Test_Video.mp4"
        assert metadata.source == "wikimedia"
        assert metadata.license == "CC-BY-4.0"
        assert "wikimedia" in metadata.s3_key  # Source should be in path
        assert "nature" in metadata.s3_key

        assert mock_s3_client.put_object.call_count == 1


def test_ingest_video_batch_empty_results(mock_s3_client, aws_config):
    """Test ingestion with no search results."""
    with patch("video_pipeline.ingest.WikimediaCommonsClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search_videos.return_value = []
        mock_client_class.return_value = mock_client

        # ingest_video_batch now returns dict separated by source
        results_by_source = ingest_video_batch(
            campaign="nonexistent",
            batch_size=5,
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        # Should return empty dict or dict with empty lists
        total_count = sum(len(metadata_list) for metadata_list in results_by_source.values())
        assert total_count == 0
        mock_s3_client.put_object.assert_not_called()


def test_video_metadata():
    """Test VideoMetadata dataclass."""
    metadata = VideoMetadata(
        source="wikimedia",
        title="File:Test_Video.mp4",
        file_url="https://example.com/video.mp4",
        license="CC-BY-4.0",
        author="testuser",
        description="Test video",
        duration=10.5,
        file_size=1024000,
        s3_key="media-raw/video/nature/20240101_120000/Test_Video.mp4",
        ingested_at="20240101_120000",
        source_id="File:Test_Video.mp4",
    )

    assert metadata.source == "wikimedia"
    assert metadata.title == "File:Test_Video.mp4"
    assert metadata.license == "CC-BY-4.0"
    assert metadata.author == "testuser"
    assert metadata.duration == 10.5
