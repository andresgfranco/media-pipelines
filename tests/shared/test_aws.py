from __future__ import annotations

import json
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from moto import mock_aws

from shared import aws as aws_utils
from shared.config import AwsConfig


@mock_aws
def test_build_aws_resources_creates_clients_with_config():
    aws_config = AwsConfig(
        region="us-east-1",
        audio_bucket="audio-bucket",
        video_bucket="video-bucket",
        metadata_table="metadata-table",
    )

    clients = aws_utils.build_aws_resources(aws_config=aws_config)

    assert set(clients.keys()) == {"s3", "dynamodb", "stepfunctions", "rekognition"}
    assert clients["s3"].meta.region_name == "us-east-1"


@mock_aws
def test_s3_storage_upload_and_list():
    resource = boto3.resource("s3", region_name="us-east-1")
    resource.create_bucket(Bucket="test-bucket")

    s3_client = boto3.client("s3", region_name="us-east-1")
    storage = aws_utils.S3Storage(s3_client)

    storage.upload_bytes(bucket="test-bucket", key="path/file.txt", data=b"data")

    keys = list(storage.list_keys(bucket="test-bucket", prefix="path"))
    assert keys == ["path/file.txt"]


def test_invoke_with_retry_retries_on_failures(monkeypatch: pytest.MonkeyPatch):
    call_count = {"count": 0}

    def flaky_operation():
        call_count["count"] += 1
        if call_count["count"] < 2:
            raise EndpointConnectionError(endpoint_url="https://example.com")
        return "success"

    result = aws_utils.invoke_with_retry(flaky_operation, max_attempts=3, base_backoff=0.0)
    assert result == "success"
    assert call_count["count"] == 2


def test_trigger_state_machine_uses_client_and_serialises_payload():
    mock_client = MagicMock()
    mock_client.start_execution.return_value = {"executionArn": "arn:aws:states::123"}

    payload = {"hello": "world"}
    response = aws_utils.trigger_state_machine(
        name="arn:aws:states:us-east-1:123:stateMachine:test",
        payload=payload,
        stepfunctions_client=mock_client,
    )

    assert response == {"executionArn": "arn:aws:states::123"}
    mock_client.start_execution.assert_called_once()
    args, kwargs = mock_client.start_execution.call_args
    assert not args
    assert kwargs["stateMachineArn"].endswith(":stateMachine:test")
    assert json.loads(kwargs["input"]) == payload
