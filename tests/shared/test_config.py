from __future__ import annotations

import os

import pytest

from shared.config import (
    DEFAULT_ENVIRONMENT,
    ENV_PREFIX,
    AwsConfig,
    MissingConfigError,
    RuntimeConfig,
    get_runtime_config,
    load_config_from_env,
    set_runtime_config,
)


def test_load_config_from_env_reads_prefixed_env_vars():
    env = {
        f"{ENV_PREFIX}ENVIRONMENT": "staging",
        f"{ENV_PREFIX}AWS_REGION": "us-west-2",
        f"{ENV_PREFIX}VIDEO_BUCKET": "video-bucket",
        f"{ENV_PREFIX}METADATA_TABLE": "media-table",
        f"{ENV_PREFIX}STEP_FUNCTIONS_ROLE_ARN": "arn:aws:iam::123:role/step-functions",
    }

    config = load_config_from_env(env)

    assert isinstance(config, RuntimeConfig)
    assert config.environment == "staging"
    assert isinstance(config.aws, AwsConfig)
    assert config.aws.region == "us-west-2"
    assert config.aws.video_bucket == "video-bucket"
    assert config.aws.metadata_table == "media-table"
    assert config.aws.step_functions_role_arn == "arn:aws:iam::123:role/step-functions"


def test_load_config_uses_defaults_and_raises_for_missing_values():
    env = {
        f"{ENV_PREFIX}VIDEO_BUCKET": "video-bucket",
        f"{ENV_PREFIX}METADATA_TABLE": "media-table",
    }

    config = load_config_from_env(env)

    assert config.environment == DEFAULT_ENVIRONMENT
    assert config.aws.region == "us-east-1"

    with pytest.raises(MissingConfigError):
        load_config_from_env({})


def test_config_cache_round_trip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(f"{ENV_PREFIX}ENVIRONMENT", raising=False)
    monkeypatch.delenv(f"{ENV_PREFIX}VIDEO_BUCKET", raising=False)
    monkeypatch.delenv(f"{ENV_PREFIX}METADATA_TABLE", raising=False)

    set_runtime_config(
        environment="local",
        video_bucket="video-test",
        metadata_table="metadata-test",
        region="us-west-1",
    )

    config = get_runtime_config()
    assert config.environment == "local"
    assert config.aws.video_bucket == "video-test"
    assert config.aws.metadata_table == "metadata-test"

    # Overwrite values and confirm cache resets.
    set_runtime_config(
        environment="dev",
        video_bucket="video-next",
        metadata_table="metadata-next",
        region="eu-west-1",
    )
    refreshed = get_runtime_config()
    assert refreshed.environment == "dev"
    assert refreshed.aws.region == "eu-west-1"

    # Clean up env variables we touched.
    for key in (
        "ENVIRONMENT",
        "AWS_REGION",
        "VIDEO_BUCKET",
        "METADATA_TABLE",
        "STEP_FUNCTIONS_ROLE_ARN",
    ):
        os.environ.pop(f"{ENV_PREFIX}{key}", None)
