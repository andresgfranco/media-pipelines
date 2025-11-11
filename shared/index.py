"""Index for processed media files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.client import BaseClient

from shared.aws import invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcessedMediaRecord:
    """Record for processed media file."""

    media_type: str  # "audio" or "video"
    campaign: str
    s3_key: str
    processed_key: str
    ingested_at: str
    processed_at: str
    metadata: dict[str, Any]


def index_processed_media(
    *,
    media_type: str,
    campaign: str,
    s3_key: str,
    processed_key: str,
    ingested_at: str,
    metadata: dict[str, Any],
    dynamodb_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> None:
    """Index a processed media file in DynamoDB."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if dynamodb_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        dynamodb_client = resources["dynamodb"]

    processed_at = datetime.now(UTC).isoformat()

    # Create composite key: media_type#campaign#timestamp
    timestamp_part = ingested_at.replace("_", "")
    item_id = f"{media_type}#{campaign}#{timestamp_part}"

    item = {
        "id": item_id,
        "media_type": media_type,
        "campaign": campaign,
        "s3_key": s3_key,
        "processed_key": processed_key,
        "ingested_at": ingested_at,
        "processed_at": processed_at,
        "metadata": metadata,
        "ttl": int(datetime.now(UTC).timestamp()) + (365 * 24 * 60 * 60),  # 1 year TTL
    }

    def _put_item() -> dict:
        import json

        dynamodb_item: dict[str, Any] = {}
        for k, v in item.items():
            if k == "metadata":
                # Store metadata as JSON string
                dynamodb_item[k] = {"S": json.dumps(v)}
            elif isinstance(v, str):
                dynamodb_item[k] = {"S": v}
            elif isinstance(v, int | float):
                dynamodb_item[k] = {"N": str(v)}
            elif isinstance(v, bool):
                dynamodb_item[k] = {"BOOL": v}
            elif isinstance(v, dict):
                dynamodb_item[k] = {"M": _dict_to_dynamodb(v)}
            else:
                dynamodb_item[k] = {"S": str(v)}

        return dynamodb_client.put_item(
            TableName=aws_config.metadata_table,
            Item=dynamodb_item,
        )

    try:
        LOGGER.info("Indexing processed media: %s", item_id)
        invoke_with_retry(_put_item, max_attempts=3)
    except Exception as e:
        LOGGER.error("Failed to index media: %s", e, exc_info=True)
        raise


def _dict_to_dynamodb(d: dict[str, Any]) -> dict[str, Any]:
    """Convert dict to DynamoDB format (simplified)."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = {"S": v}
        elif isinstance(v, int | float):
            result[k] = {"N": str(v)}
        elif isinstance(v, bool):
            result[k] = {"BOOL": v}
        elif isinstance(v, dict):
            result[k] = {"M": _dict_to_dynamodb(v)}
        elif isinstance(v, list):
            result[k] = {"L": [_dict_to_dynamodb({"item": item})["item"] for item in v]}
    return result


def query_processed_media(
    *,
    campaign: str | None = None,
    media_type: str | None = None,
    limit: int = 100,
    dynamodb_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> list[ProcessedMediaRecord]:
    """Query processed media records."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if dynamodb_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        dynamodb_client = resources["dynamodb"]

    # Simple scan for now (would use GSI in production)
    scan_params: dict[str, Any] = {
        "TableName": aws_config.metadata_table,
        "Limit": limit,
    }

    def _scan() -> dict:
        return dynamodb_client.scan(**scan_params)

    try:
        response = invoke_with_retry(_scan, max_attempts=3)
        items = response.get("Items", [])

        records = []
        for item in items:
            # Filter by campaign and media_type if specified
            item_campaign = item.get("campaign", {}).get("S", "")
            item_type = item.get("media_type", {}).get("S", "")

            if campaign and item_campaign != campaign:
                continue
            if media_type and item_type != media_type:
                continue

            # Parse metadata (stored as JSON string)
            metadata_str = item.get("metadata", {}).get("S", "{}")
            try:
                import json

                metadata = json.loads(metadata_str)
            except Exception:
                metadata = {}

            record = ProcessedMediaRecord(
                media_type=item_type,
                campaign=item_campaign,
                s3_key=item.get("s3_key", {}).get("S", ""),
                processed_key=item.get("processed_key", {}).get("S", ""),
                ingested_at=item.get("ingested_at", {}).get("S", ""),
                processed_at=item.get("processed_at", {}).get("S", ""),
                metadata=metadata,
            )
            records.append(record)

        return records
    except Exception as e:
        LOGGER.error("Failed to query processed media: %s", e, exc_info=True)
        return []
