"""Tests for audio ingestion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.client import BaseClient

from audio_pipeline.ingest import (
    AudioMetadata,
    InternetArchiveClient,
    ingest_audio_batch,
)
from shared.config import AwsConfig


@pytest.fixture
def mock_internet_archive_search_response():
    """Mock Internet Archive API search response."""
    return {
        "response": {
            "docs": [
                {
                    "identifier": "test-item-1",
                    "title": "Test Sound",
                    "creator": "testuser",
                    "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                    "downloads": 100,
                },
                {
                    "identifier": "test-item-2",
                    "title": "Another Sound",
                    "creator": "anotheruser",
                    "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "downloads": 50,
                },
            ]
        }
    }


@pytest.fixture
def mock_internet_archive_metadata():
    """Mock Internet Archive metadata response."""
    return {
        "metadata": {
            "identifier": "test-item-1",
            "title": "Test Sound",
            "creator": "testuser",
        },
        "files": [
            {
                "name": "test-sound.mp3",
                "format": "VBR MP3",
                "size": "102400",
                "length": "5.5",
            }
        ],
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


def test_internet_archive_client_search(mock_internet_archive_search_response):
    """Test Internet Archive client search."""
    with patch("audio_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_internet_archive_search_response
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = InternetArchiveClient()
        results = client.search("nature", rows=2)

        assert len(results) == 2
        assert results[0]["identifier"] == "test-item-1"
        assert results[0]["title"] == "Test Sound"
        assert results[1]["identifier"] == "test-item-2"


def test_internet_archive_client_get_metadata(mock_internet_archive_metadata):
    """Test Internet Archive client get metadata."""
    with patch("audio_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_internet_archive_metadata
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = InternetArchiveClient()
        metadata = client.get_metadata("test-item-1")

        assert metadata["metadata"]["identifier"] == "test-item-1"
        assert len(metadata["files"]) == 1


def test_internet_archive_client_download_file():
    """Test Internet Archive client download."""
    with patch("audio_pipeline.ingest.requests.Session") as mock_session:
        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = InternetArchiveClient()
        data = client.download_file("test-item-1", "test-sound.mp3")

        assert data == b"fake audio data"


def test_internet_archive_client_select_audio_file():
    """Test Internet Archive client file selection."""
    client = InternetArchiveClient()

    files = [
        {"name": "short.mp3", "format": "VBR MP3", "length": "0.1", "size": "1000"},
        {"name": "good.mp3", "format": "VBR MP3", "length": "5.5", "size": "102400"},
        {"name": "long.mp3", "format": "VBR MP3", "length": "120", "size": "204800"},
        {"name": "ogg.ogg", "format": "OGG VORBIS", "length": "3.2", "size": "51200"},
    ]

    selected = client.select_audio_file(files)
    assert selected is not None
    assert selected["name"] == "good.mp3"  # Should select VBR MP3 with valid duration


@patch("audio_pipeline.ingest.get_runtime_config")
def test_ingest_audio_batch(
    mock_get_config,
    mock_internet_archive_search_response,
    mock_internet_archive_metadata,
    mock_s3_client,
    aws_config,
):
    """Test audio batch ingestion."""
    mock_get_config.return_value.aws = aws_config

    with patch("audio_pipeline.ingest.InternetArchiveClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_internet_archive_search_response["response"]["docs"]
        mock_client.get_metadata.return_value = mock_internet_archive_metadata
        mock_client.select_audio_file.return_value = mock_internet_archive_metadata["files"][0]
        mock_client.download_file.side_effect = [
            b"fake audio data 1",
            b"fake audio data 2",
        ]
        mock_client_class.return_value = mock_client

        metadata_list = ingest_audio_batch(
            campaign="nature",
            batch_size=2,
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        assert len(metadata_list) == 2
        assert metadata_list[0].archive_id == "test-item-1"
        assert metadata_list[0].title == "Test Sound"
        assert "nature" in metadata_list[0].s3_key
        assert metadata_list[1].archive_id == "test-item-2"

        # Verify S3 uploads were called
        assert mock_s3_client.put_object.call_count == 2


def test_ingest_audio_batch_empty_results(mock_s3_client, aws_config):
    """Test ingestion with no search results."""
    with patch("audio_pipeline.ingest.InternetArchiveClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client_class.return_value = mock_client

        metadata_list = ingest_audio_batch(
            campaign="nonexistent",
            batch_size=5,
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )

        assert len(metadata_list) == 0
        mock_s3_client.put_object.assert_not_called()


def test_audio_metadata():
    """Test AudioMetadata dataclass."""
    metadata = AudioMetadata(
        archive_id="test-item-1",
        title="Test Sound",
        author="testuser",
        license="https://creativecommons.org/licenses/by/4.0/",
        url="https://archive.org/details/test-item-1",
        duration=5.5,
        file_size=102400,
        tags=[],
        s3_key="media-raw/audio/nature/20240101_120000/test-item-1_test-sound.mp3",
        ingested_at="20240101_120000",
    )

    assert metadata.archive_id == "test-item-1"
    assert metadata.title == "Test Sound"
    assert metadata.author == "testuser"
    assert metadata.license == "https://creativecommons.org/licenses/by/4.0/"
