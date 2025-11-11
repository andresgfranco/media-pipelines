"""Tests for Rekognition Video integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.client import BaseClient

from shared.config import AwsConfig
from video_pipeline.finalize import (
    VideoAnalysis,
    VideoLabel,
    finalize_video_analysis,
    normalize_rekognition_labels,
    save_analysis_to_s3,
)
from video_pipeline.rekognition import RekognitionJob, get_job_status, start_label_detection_job


@pytest.fixture
def mock_rekognition_client():
    """Mock Rekognition client."""
    client = MagicMock(spec=BaseClient)
    client.start_label_detection = MagicMock(return_value={"JobId": "test-job-123"})
    client.get_label_detection = MagicMock(
        return_value={
            "JobStatus": "SUCCEEDED",
            "VideoMetadata": {"DurationMillis": 10000},
            "Labels": [
                {
                    "Label": {
                        "Name": "Person",
                        "Confidence": 95.5,
                        "Instances": [{"BoundingBox": {}}],
                    },
                    "Timestamp": 5000,
                },
                {
                    "Label": {
                        "Name": "Outdoor",
                        "Confidence": 88.2,
                    },
                    "Timestamp": 3000,
                },
            ],
            "ModerationLabels": [],
        }
    )
    return client


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


def test_start_label_detection_job(mock_rekognition_client, aws_config):
    """Test starting a Rekognition label detection job."""
    job = start_label_detection_job(
        video_s3_bucket="test-bucket",
        video_s3_key="test-video.mp4",
        rekognition_client=mock_rekognition_client,
        aws_config=aws_config,
    )

    assert isinstance(job, RekognitionJob)
    assert job.job_id == "test-job-123"
    assert job.status == "IN_PROGRESS"
    assert job.video_s3_key == "test-video.mp4"
    assert job.video_s3_bucket == "test-bucket"

    mock_rekognition_client.start_label_detection.assert_called_once()


def test_get_job_status(mock_rekognition_client, aws_config):
    """Test getting Rekognition job status."""
    status = get_job_status(
        job_id="test-job-123",
        rekognition_client=mock_rekognition_client,
        aws_config=aws_config,
    )

    assert status["JobStatus"] == "SUCCEEDED"
    assert "Labels" in status
    assert len(status["Labels"]) == 2
    mock_rekognition_client.get_label_detection.assert_called_once_with(JobId="test-job-123")


def test_normalize_rekognition_labels():
    """Test normalizing Rekognition labels."""
    rekognition_response = {
        "Labels": [
            {
                "Label": {
                    "Name": "Person",
                    "Confidence": 95.5,
                    "Instances": [{"BoundingBox": {}}],
                },
                "Timestamp": 5000,
            }
        ]
    }

    labels = normalize_rekognition_labels(rekognition_response)

    assert len(labels) == 1
    assert labels[0].name == "Person"
    assert labels[0].confidence == 95.5
    assert labels[0].timestamp == 5.0


def test_finalize_video_analysis(mock_rekognition_client, mock_s3_client, aws_config):
    """Test finalizing video analysis."""
    analysis = finalize_video_analysis(
        job_id="test-job-123",
        video_s3_key="test-video.mp4",
        rekognition_client=mock_rekognition_client,
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    assert isinstance(analysis, VideoAnalysis)
    assert analysis.video_s3_key == "test-video.mp4"
    assert analysis.duration == 10.0
    assert len(analysis.labels) == 2
    assert analysis.labels[0].name == "Person"
    assert analysis.summary["total_labels"] == 2
    assert len(analysis.summary["top_labels"]) == 2


def test_finalize_video_analysis_failed_job(mock_rekognition_client, mock_s3_client, aws_config):
    """Test finalizing video analysis with failed job."""
    mock_rekognition_client.get_label_detection.return_value = {
        "JobStatus": "FAILED",
        "StatusMessage": "Job failed",
    }

    with pytest.raises(RuntimeError, match="did not succeed"):
        finalize_video_analysis(
            job_id="test-job-123",
            video_s3_key="test-video.mp4",
            rekognition_client=mock_rekognition_client,
            s3_client=mock_s3_client,
            aws_config=aws_config,
        )


@patch("video_pipeline.finalize.S3Storage")
def test_save_analysis_to_s3(mock_storage_class, mock_s3_client, aws_config):
    """Test saving analysis results to S3."""
    mock_storage = MagicMock()
    mock_storage_class.return_value = mock_storage

    analysis = VideoAnalysis(
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

    save_analysis_to_s3(
        analysis=analysis,
        bucket="test-bucket",
        key="test-analysis.json",
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    mock_storage.upload_bytes.assert_called_once()
    call_args = mock_storage.upload_bytes.call_args
    assert call_args.kwargs["bucket"] == "test-bucket"
    assert call_args.kwargs["key"] == "test-analysis.json"
    assert call_args.kwargs["content_type"] == "application/json"
