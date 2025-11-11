"""Notification helpers for pipeline events."""

from __future__ import annotations

import json
import logging
from typing import Any

from botocore.client import BaseClient

from shared.aws import invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)


def send_pipeline_notification(
    *,
    topic_arn: str,
    pipeline_type: str,
    campaign: str,
    status: str,
    execution_arn: str | None = None,
    error_message: str | None = None,
    sns_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> dict[str, Any]:
    """Send SNS notification about pipeline execution."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if sns_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        sns_client = resources.get("sns")

        if sns_client is None:
            from shared.aws import AwsSessionFactory

            factory = AwsSessionFactory(region=aws_config.region)
            sns_client = factory.client("sns")

    subject = f"Media Pipeline {pipeline_type.upper()}: {status}"

    message = {
        "pipeline_type": pipeline_type,
        "campaign": campaign,
        "status": status,
        "execution_arn": execution_arn,
    }

    if error_message:
        message["error"] = error_message

    def _publish() -> dict:
        return sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=json.dumps(message, indent=2),
        )

    try:
        LOGGER.info("Sending notification to %s: %s", topic_arn, subject)
        response = invoke_with_retry(_publish, max_attempts=3)
        return response
    except Exception as e:
        LOGGER.error("Failed to send notification: %s", e, exc_info=True)
        raise
