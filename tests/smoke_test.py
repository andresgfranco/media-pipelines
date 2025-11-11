"""Smoke tests to verify core functionality."""

from __future__ import annotations

import pytest
from moto import mock_aws

from shared.aws import build_aws_resources, trigger_state_machine
from shared.config import AwsConfig, set_runtime_config
from shared.index import index_processed_media, query_processed_media
from shared.notifications import send_pipeline_notification


@pytest.fixture(autouse=True)
def setup_config():
    """Set up runtime configuration for smoke tests."""
    set_runtime_config(
        environment="test",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
        region="us-east-1",
    )
    yield
    from shared.config import get_runtime_config

    get_runtime_config.cache_clear()


@mock_aws
def test_aws_resources_creation():
    """Smoke test: Verify AWS resources can be created."""
    aws_config = AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )

    resources = build_aws_resources(aws_config=aws_config)

    assert "s3" in resources
    assert "dynamodb" in resources
    assert "stepfunctions" in resources
    assert "rekognition" in resources
    assert "sns" in resources


@mock_aws
def test_indexing_workflow():
    """Smoke test: Verify indexing workflow."""
    from shared.aws import build_aws_resources

    aws_config = AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )

    resources = build_aws_resources(aws_config=aws_config)
    dynamodb = resources["dynamodb"]

    # Create table
    dynamodb.create_table(
        TableName=aws_config.metadata_table,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # Index media
    index_processed_media(
        media_type="video",
        campaign="nature",
        s3_key="media-raw/video/wikimedia/nature/20240101_120000/test.mp4",
        processed_key="media-processed/video/wikimedia/nature/20240101_120000/test_labels.json",
        ingested_at="20240101_120000",
        metadata={"labels": [{"Name": "Nature", "Confidence": 95.5}]},
        aws_config=aws_config,
    )

    # Query indexed media
    records = query_processed_media(campaign="nature", aws_config=aws_config)
    assert len(records) == 1
    assert records[0].media_type == "video"
    assert records[0].campaign == "nature"


@mock_aws
def test_notification_system():
    """Smoke test: Verify notification system."""
    from unittest.mock import MagicMock

    mock_sns = MagicMock()
    mock_sns.publish = MagicMock(return_value={"MessageId": "test-id"})

    aws_config = AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )

    result = send_pipeline_notification(
        topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
        pipeline_type="video",
        campaign="nature",
        status="SUCCEEDED",
        sns_client=mock_sns,
        aws_config=aws_config,
    )

    assert result["MessageId"] == "test-id"
    mock_sns.publish.assert_called_once()


@mock_aws
def test_state_machine_trigger():
    """Smoke test: Verify state machine can be triggered."""
    from shared.aws import build_aws_resources

    aws_config = AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )

    resources = build_aws_resources(aws_config=aws_config)
    stepfunctions = resources["stepfunctions"]

    # Create state machine
    create_response = stepfunctions.create_state_machine(
        name="test-state-machine",
        definition='{"StartAt": "Pass", "States": {"Pass": {"Type": "Pass", "End": true}}}',
        roleArn="arn:aws:iam::123456789012:role/test-role",
    )
    state_machine_arn = create_response["stateMachineArn"]

    # Trigger state machine
    result = trigger_state_machine(
        name=state_machine_arn,
        payload={"test": "data"},
        stepfunctions_client=stepfunctions,
        aws_config=aws_config,
    )

    assert "executionArn" in result


def test_imports():
    """Smoke test: Verify all main modules can be imported."""
    # Video pipeline
    from video_pipeline import finalize, ingest, rekognition

    assert ingest is not None
    assert rekognition is not None
    assert finalize is not None

    # Shared utilities
    from shared import aws, config, index, notifications

    assert aws is not None
    assert config is not None
    assert index is not None
    assert notifications is not None

    # Infrastructure handlers
    from infrastructure.handlers import (
        index_video,
        video_ingest,
        video_rekognition_check,
        video_rekognition_finalize,
        video_rekognition_start,
    )

    assert video_ingest is not None
    assert video_rekognition_start is not None
    assert video_rekognition_check is not None
    assert video_rekognition_finalize is not None
    assert index_video is not None
