"""Utilities for interacting with AWS services."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, EndpointConnectionError

from .config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class Retryable(Protocol):
    """Callable protocol for retry helpers."""

    def __call__(self) -> T:  # pragma: no cover - Protocol definition
        ...


def invoke_with_retry(
    operation: Retryable,
    *,
    max_attempts: int = 3,
    base_backoff: float = 0.5,
    backoff_jitter: float = 0.25,
    retryable_errors: Sequence[type[Exception]] = (
        ClientError,
        EndpointConnectionError,
    ),
) -> T:
    """Invoke ``operation`` with exponential backoff and jitter."""

    attempt = 0
    while True:
        try:
            return operation()
        except retryable_errors:  # type: ignore[arg-type]
            attempt += 1
            if attempt >= max_attempts:
                LOGGER.exception("Exceeded max retries (%s) on AWS operation", max_attempts)
                raise
            sleep_for = base_backoff * (2 ** (attempt - 1))
            sleep_for += random.uniform(0, backoff_jitter)
            LOGGER.warning("Retrying AWS operation (attempt %s/%s)...", attempt, max_attempts)
            time.sleep(sleep_for)


@dataclass(slots=True)
class AwsSessionFactory:
    """Factory for lazily creating boto3 sessions and clients."""

    region: str
    profile: str | None = None

    def _session(self) -> boto3.session.Session:
        if self.profile:
            return boto3.session.Session(profile_name=self.profile, region_name=self.region)
        return boto3.session.Session(region_name=self.region)

    def client(self, service: str, *, config: BotoConfig | None = None) -> BaseClient:
        session = self._session()
        return session.client(service, config=config)


class S3Storage:
    """Simple helper around S3 uploads and downloads."""

    def __init__(self, client: BaseClient, *, default_acl: str = "private") -> None:
        self._client = client
        self._default_acl = default_acl

    def upload_bytes(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        def _put_object() -> dict[str, str]:
            put_params: dict[str, object] = {
                "Bucket": bucket,
                "Key": key,
                "Body": data,
                "Metadata": metadata or {},
                "ACL": self._default_acl,
            }
            if content_type:
                put_params["ContentType"] = content_type
            return self._client.put_object(**put_params)

        invoke_with_retry(_put_object)

    def list_keys(self, *, bucket: str, prefix: str | None = None) -> Iterable[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix or ""):
            for item in page.get("Contents", []):
                yield item["Key"]


def build_aws_resources(
    *,
    aws_config: AwsConfig | None = None,
    boto_config: BotoConfig | None = None,
) -> dict[str, BaseClient]:
    """Create common AWS clients using runtime configuration."""

    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    session_factory = AwsSessionFactory(region=aws_config.region)
    boto_cfg = boto_config or BotoConfig(retries={"mode": "standard", "max_attempts": 3})

    clients = {
        "s3": session_factory.client("s3", config=boto_cfg),
        "dynamodb": session_factory.client("dynamodb", config=boto_cfg),
        "stepfunctions": session_factory.client("stepfunctions", config=boto_cfg),
    }
    return clients


def trigger_state_machine(
    *,
    name: str,
    payload: dict,
    stepfunctions_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> dict:
    """Start a Step Functions execution with retry handling."""

    if stepfunctions_client is None:
        clients = build_aws_resources(aws_config=aws_config)
        stepfunctions_client = clients["stepfunctions"]

    def _start_execution() -> dict:
        return stepfunctions_client.start_execution(stateMachineArn=name, input=json_dump(payload))

    return invoke_with_retry(_start_execution)


def json_dump(payload: dict) -> str:
    """Serialize a payload to JSON; kept separate for testability."""
    import json

    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
