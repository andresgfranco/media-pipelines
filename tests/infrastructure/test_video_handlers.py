"""Integration tests for video pipeline Lambda handlers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from moto import mock_aws

from infrastructure.handlers.video_ingest import handler as ingest_handler
from infrastructure.handlers.video_rekognition_check import (
    handler as check_handler,
)
from infrastructure.handlers.video_rekognition_finalize import (
    handler as finalize_handler,
)
from infrastructure.handlers.video_rekognition_start import (
    handler as start_handler,
)
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
@patch("infrastructure.handlers.video_ingest.ingest_video_batch")
def test_video_ingest_handler_success(mock_ingest, aws_config):
    """Test successful video ingestion handler."""
    mock_metadata = [
        MagicMock(
            wikimedia_title="File:Test_Video.mp4",
            file_url="https://example.com/video.mp4",
            license="CC-BY-4.0",
            author="testuser",
            description="Test video",
            duration=10.5,
            file_size=1024000,
            s3_key="media-raw/video/nature/20240101_120000/Test_Video.mp4",
            ingested_at="20240101_120000",
        )
    ]
    mock_ingest.return_value = mock_metadata

    event = {
        "campaign": "nature",
        "batch_size_video": 2,
    }

    result = ingest_handler(event, MagicMock())

    assert result["campaign"] == "nature"
    assert result["batch_size"] == 2
    assert result["ingested_count"] == 1
    assert len(result["metadata"]) == 1
    assert result["metadata"][0]["wikimedia_title"] == "File:Test_Video.mp4"


@mock_aws
@patch("infrastructure.handlers.video_rekognition_start.start_label_detection_job")
def test_rekognition_start_handler_success(mock_start, aws_config):
    """Test successful Rekognition job start handler."""
    from video_pipeline.rekognition import RekognitionJob

    mock_job = RekognitionJob(
        job_id="test-job-123",
        status="IN_PROGRESS",
        video_s3_key="test-video.mp4",
        video_s3_bucket="test-bucket",
    )
    mock_start.return_value = mock_job

    event = {
        "campaign": "nature",
        "metadata": [
            {
                "s3_key": "media-raw/video/nature/20240101_120000/Test_Video.mp4",
            }
        ],
    }

    result = start_handler(event, MagicMock())

    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["job_id"] == "test-job-123"
    assert result["campaign"] == "nature"


@mock_aws
@patch("infrastructure.handlers.video_rekognition_check.get_job_status")
def test_rekognition_check_handler_success(mock_get_status, aws_config):
    """Test successful Rekognition job status check handler."""
    mock_get_status.return_value = {
        "JobStatus": "SUCCEEDED",
        "StatusMessage": "",
        "VideoMetadata": {"DurationMillis": 10000},
        "Labels": [],
    }

    event = {
        "job_id": "test-job-123",
    }

    result = check_handler(event, MagicMock())

    assert result["JobStatus"] == "SUCCEEDED"
    assert "Labels" in result


@mock_aws
@patch("infrastructure.handlers.video_rekognition_finalize.finalize_video_analysis")
@patch("infrastructure.handlers.video_rekognition_finalize.save_analysis_to_s3")
def test_rekognition_finalize_handler_success(mock_save, mock_finalize, aws_config):
    """Test successful Rekognition finalization handler."""
    from video_pipeline.finalize import VideoAnalysis, VideoLabel

    mock_analysis = VideoAnalysis(
        video_s3_key="test-video.mp4",
        duration=10.0,
        labels=[
            VideoLabel(
                name="Person",
                confidence=95.5,
                timestamp=5.0,
                instances=[],
            )
        ],
        moderation_labels=[],
        summary={"total_labels": 1},
    )
    mock_finalize.return_value = mock_analysis

    event = {
        "campaign": "nature",
        "jobs": [
            {
                "job_id": "test-job-123",
                "video_s3_key": "media-raw/video/nature/20240101_120000/Test_Video.mp4",
            }
        ],
    }

    result = finalize_handler(event, MagicMock())

    assert result["campaign"] == "nature"
    assert result["processed_count"] == 1
    assert len(result["results"]) == 1
    assert mock_finalize.call_count == 1
    assert mock_save.call_count == 1
