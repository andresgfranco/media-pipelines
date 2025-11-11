"""Configuration helpers for media pipelines."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from functools import lru_cache


class MissingConfigError(RuntimeError):
    """Raised when a required configuration value is missing."""


@dataclass(frozen=True, slots=True)
class AwsConfig:
    """AWS-related configuration values."""

    region: str
    video_bucket: str
    metadata_table: str
    step_functions_role_arn: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Application runtime configuration."""

    environment: str
    aws: AwsConfig


DEFAULT_ENVIRONMENT = "local"
ENV_PREFIX = "MEDIA_PIPELINES_"


def _get_env(mapping: Mapping[str, str], key: str, *, default: str | None = None) -> str:
    """Fetch a value from the mapping or raise if it is missing."""
    if key in mapping:
        return mapping[key]
    if default is not None:
        return default
    raise MissingConfigError(f"Missing required configuration value: {key}")


def _apply_prefix(key: str) -> str:
    """Apply the default prefix to the environment variable name."""
    if key.startswith(ENV_PREFIX):
        return key
    return f"{ENV_PREFIX}{key}"


def load_config_from_env(
    env: Mapping[str, str] | None = None,
    *,
    prefix: str = ENV_PREFIX,
) -> RuntimeConfig:
    """Load configuration from a mapping (defaults to the OS environment)."""

    env_mapping: Mapping[str, str] = os.environ if env is None else env

    def resolve(name: str, *, default: str | None = None) -> str:
        raw_key = f"{prefix}{name}"
        return _get_env(env_mapping, raw_key, default=default)

    aws_config = AwsConfig(
        region=resolve("AWS_REGION", default="us-east-1"),
        video_bucket=resolve("VIDEO_BUCKET"),
        metadata_table=resolve("METADATA_TABLE"),
        step_functions_role_arn=env_mapping.get(f"{prefix}STEP_FUNCTIONS_ROLE_ARN"),
    )
    runtime_config = RuntimeConfig(
        environment=resolve("ENVIRONMENT", default=DEFAULT_ENVIRONMENT),
        aws=aws_config,
    )
    return runtime_config


@lru_cache(maxsize=1)
def get_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    prefix: str = ENV_PREFIX,
) -> RuntimeConfig:
    """Cached wrapper around :func:`load_config_from_env`."""

    return load_config_from_env(env=env, prefix=prefix)


def set_runtime_config(
    *,
    environment: str,
    video_bucket: str,
    metadata_table: str,
    region: str = "us-east-1",
    step_functions_role_arn: str | None = None,
    env: MutableMapping[str, str] | None = None,
    prefix: str = ENV_PREFIX,
) -> None:
    """Utility to seed configuration values for local development or tests."""

    target_env: MutableMapping[str, str]
    if env is None:
        target_env = os.environ
    else:
        target_env = env

    target_env[f"{prefix}ENVIRONMENT"] = environment
    target_env[f"{prefix}AWS_REGION"] = region
    target_env[f"{prefix}VIDEO_BUCKET"] = video_bucket
    target_env[f"{prefix}METADATA_TABLE"] = metadata_table

    if step_functions_role_arn:
        target_env[f"{prefix}STEP_FUNCTIONS_ROLE_ARN"] = step_functions_role_arn
    else:
        target_env.pop(f"{prefix}STEP_FUNCTIONS_ROLE_ARN", None)

    # Reset cached config so the next caller sees updated values.
    get_runtime_config.cache_clear()
