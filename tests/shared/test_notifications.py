"""Tests for notification helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.client import BaseClient

from shared.config import AwsConfig
from shared.notifications import send_pipeline_notification


@pytest.fixture
def mock_sns_client():
    """Mock SNS client."""
    client = MagicMock(spec=BaseClient)
    client.publish = MagicMock(return_value={"MessageId": "test-message-id"})
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


def test_send_pipeline_notification_success(mock_sns_client, aws_config):
    """Test successful pipeline notification."""
    result = send_pipeline_notification(
        topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
        pipeline_type="audio",
        campaign="nature",
        status="SUCCEEDED",
        execution_arn="arn:aws:states:us-east-1:123456789012:execution:test",
        sns_client=mock_sns_client,
        aws_config=aws_config,
    )

    assert result["MessageId"] == "test-message-id"
    mock_sns_client.publish.assert_called_once()
    call_args = mock_sns_client.publish.call_args
    assert call_args.kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:test-topic"
    assert "SUCCEEDED" in call_args.kwargs["Subject"]


def test_send_pipeline_notification_with_error(mock_sns_client, aws_config):
    """Test pipeline notification with error message."""
    result = send_pipeline_notification(
        topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
        pipeline_type="video",
        campaign="tech",
        status="FAILED",
        error_message="Test error",
        sns_client=mock_sns_client,
        aws_config=aws_config,
    )

    assert result["MessageId"] == "test-message-id"
    call_args = mock_sns_client.publish.call_args
    message = call_args.kwargs["Message"]
    assert "error" in message.lower()
    assert "Test error" in message
