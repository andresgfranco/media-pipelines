"""Integration tests for audio pipeline Lambda handlers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from moto import mock_aws

from infrastructure.handlers.audio_analyze import handler as analyze_handler
from infrastructure.handlers.audio_ingest import handler as ingest_handler
from shared.config import AwsConfig, set_runtime_config


@pytest.fixture
def aws_config():
    """Test AWS configuration."""
    return AwsConfig(
        region="us-east-1",
        audio_bucket="test-audio-bucket",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )


@pytest.fixture(autouse=True)
def setup_config(aws_config):
    """Set up runtime configuration for tests."""
    set_runtime_config(
        environment="test",
        audio_bucket=aws_config.audio_bucket,
        video_bucket=aws_config.video_bucket,
        metadata_table=aws_config.metadata_table,
        region=aws_config.region,
    )
    yield
    # Cleanup
    from shared.config import get_runtime_config

    get_runtime_config.cache_clear()


@mock_aws
@patch("infrastructure.handlers.audio_ingest.ingest_audio_batch")
def test_audio_ingest_handler_success(mock_ingest, aws_config):
    """Test successful audio ingestion handler."""
    mock_metadata = [
        MagicMock(
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
    ]
    mock_ingest.return_value = mock_metadata

    event = {
        "campaign": "nature",
        "batch_size_audio": 5,
    }

    result = ingest_handler(event, MagicMock())

    assert result["campaign"] == "nature"
    assert result["batch_size"] == 5
    assert result["ingested_count"] == 1
    assert len(result["metadata"]) == 1
    assert result["metadata"][0]["archive_id"] == "test-item-1"


@mock_aws
@patch("infrastructure.handlers.audio_analyze.process_audio_batch")
def test_audio_analyze_handler_success(mock_process, aws_config):
    """Test successful audio analysis handler."""
    mock_results = [
        {
            "s3_key": "media-raw/audio/nature/20240101_120000/test-item-1_test-sound.mp3",
            "processed_key": "media-processed/audio/nature/20240101_120000/test-item-1_test-sound_summary.json",
            "analysis": {
                "duration": 5.5,
                "rms_loudness": 0.2,
                "is_voice": True,
                "requires_attribution": True,
                "sample_rate": 22050,
                "channels": 1,
            },
        }
    ]
    mock_process.return_value = mock_results

    event = {
        "campaign": "nature",
        "metadata": [
            {
                "archive_id": "test-item-1",
                "s3_key": "media-raw/audio/nature/20240101_120000/test-item-1_test-sound.mp3",
                "ingested_at": "20240101_120000",
            }
        ],
    }

    result = analyze_handler(event, MagicMock())

    assert result["campaign"] == "nature"
    assert result["processed_count"] == 1
    assert len(result["results"]) == 1
    assert (
        result["results"][0]["s3_key"]
        == "media-raw/audio/nature/20240101_120000/test-item-1_test-sound.mp3"
    )


@mock_aws
def test_audio_analyze_handler_empty_metadata(aws_config):
    """Test audio analysis handler with empty metadata."""
    event = {
        "campaign": "nature",
        "metadata": [],
    }

    result = analyze_handler(event, MagicMock())

    assert result["campaign"] == "nature"
    assert result["processed_count"] == 0
    assert result["results"] == []
