"""Tests for audio ingestion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.client import BaseClient

from audio_pipeline.ingest import (
    AudioMetadata,
    FreesoundClient,
    ingest_audio_batch,
)
from shared.config import AwsConfig


@pytest.fixture
def mock_freesound_response():
    """Mock Freesound API search response."""
    return {
        "results": [
            {
                "id": 12345,
                "name": "Test Sound",
                "username": "testuser",
                "license": "cc-by",
                "url": "https://freesound.org/people/testuser/sounds/12345/",
                "duration": 5.5,
                "filesize": 102400,
                "tags": ["test", "demo"],
            },
            {
                "id": 67890,
                "name": "Another Sound",
                "username": "anotheruser",
                "license": "cc0",
                "url": "https://freesound.org/people/anotheruser/sounds/67890/",
                "duration": 3.2,
                "filesize": 51200,
                "tags": ["music"],
            },
        ]
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
        audio_bucket="test-audio-bucket",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )


def test_freesound_client_search(mock_freesound_response):
    """Test Freesound client search."""
    with patch("audio_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_freesound_response
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = FreesoundClient("test-api-key")
        results = client.search("nature", page_size=2)

        assert len(results) == 2
        assert results[0]["id"] == 12345
        assert results[0]["name"] == "Test Sound"
        assert results[1]["id"] == 67890


def test_freesound_client_download_preview():
    """Test Freesound client download."""
    with patch("audio_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = FreesoundClient("test-api-key")
        data = client.download_preview(12345)

        assert data == b"fake audio data"


@patch("audio_pipeline.ingest.get_runtime_config")
def test_ingest_audio_batch(
    mock_get_config,
    mock_freesound_response,
    mock_s3_client,
    aws_config,
):
    """Test audio batch ingestion."""
    mock_get_config.return_value.aws = aws_config

    with patch("audio_pipeline.ingest.FreesoundClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_freesound_response["results"]
        mock_client.download_preview.side_effect = [
            b"fake audio data 1",
            b"fake audio data 2",
        ]
        mock_client_class.return_value = mock_client

        metadata_list = ingest_audio_batch(
            campaign="nature",
            batch_size=2,
            freesound_api_key="test-key",
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        assert len(metadata_list) == 2
        assert metadata_list[0].freesound_id == 12345
        assert metadata_list[0].title == "Test Sound"
        assert "nature" in metadata_list[0].s3_key
        assert metadata_list[1].freesound_id == 67890

        # Verify S3 uploads were called
        assert mock_s3_client.put_object.call_count == 2


def test_ingest_audio_batch_empty_results(mock_s3_client, aws_config):
    """Test ingestion with no search results."""
    with patch("audio_pipeline.ingest.FreesoundClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client_class.return_value = mock_client

        metadata_list = ingest_audio_batch(
            campaign="nonexistent",
            batch_size=5,
            freesound_api_key="test-key",
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        assert len(metadata_list) == 0
        mock_s3_client.put_object.assert_not_called()


def test_audio_metadata():
    """Test AudioMetadata dataclass."""
    metadata = AudioMetadata(
        freesound_id=12345,
        title="Test Sound",
        author="testuser",
        license="cc-by",
        url="https://example.com/sound",
        duration=5.5,
        file_size=102400,
        tags=["test", "demo"],
        s3_key="media-raw/audio/nature/20240101_120000/12345.mp3",
        ingested_at="20240101_120000",
    )

    assert metadata.freesound_id == 12345
    assert metadata.title == "Test Sound"
    assert metadata.author == "testuser"
    assert metadata.license == "cc-by"
