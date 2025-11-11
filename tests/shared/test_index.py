"""Tests for index module."""

from __future__ import annotations

import pytest
from moto import mock_aws

from shared.config import AwsConfig, set_runtime_config
from shared.index import index_processed_media, query_processed_media


@pytest.fixture
def aws_config():
    """Test AWS configuration."""
    return AwsConfig(
        region="us-east-1",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )


@pytest.fixture(autouse=True)
def setup_config(aws_config):
    """Set up runtime configuration for tests."""
    set_runtime_config(
        environment="test",
        video_bucket=aws_config.video_bucket,
        metadata_table=aws_config.metadata_table,
        region=aws_config.region,
    )
    yield
    from shared.config import get_runtime_config

    get_runtime_config.cache_clear()


@mock_aws
def test_query_processed_media(aws_config):
    """Test querying processed media."""
    from shared.aws import build_aws_resources

    resources = build_aws_resources(aws_config=aws_config)
    dynamodb = resources["dynamodb"]

    # Create table
    dynamodb.create_table(
        TableName=aws_config.metadata_table,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # Index some media
    index_processed_media(
        media_type="video",
        campaign="nature",
        s3_key="media-raw/video/nature/20240101_120000/test1.mp4",
        processed_key="media-processed/video/nature/20240101_120000/test1.json",
        ingested_at="20240101_120000",
        metadata={"duration": 30.0},
        aws_config=aws_config,
    )

    index_processed_media(
        media_type="video",
        campaign="tech",
        s3_key="media-raw/video/tech/20240101_120000/test2.mp4",
        processed_key="media-processed/video/tech/20240101_120000/test2.json",
        ingested_at="20240101_120000",
        metadata={"duration": 45.0},
        aws_config=aws_config,
    )

    # Query all
    records = query_processed_media(aws_config=aws_config)
    assert len(records) == 2

    # Query by campaign
    records = query_processed_media(campaign="nature", aws_config=aws_config)
    assert len(records) == 1

    # Query by media_type
    records = query_processed_media(media_type="video", aws_config=aws_config)
    assert len(records) == 2
    assert records[0].media_type == "video"
