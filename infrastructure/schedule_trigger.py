"""Script to simulate scheduled pipeline triggers."""

from __future__ import annotations

import json
import logging
import sys

from shared.aws import trigger_state_machine
from shared.config import get_runtime_config

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def trigger_audio_pipeline(campaign: str, batch_size_audio: int) -> dict:
    """Trigger audio pipeline execution."""
    import os

    runtime_config = get_runtime_config()
    aws_config = runtime_config.aws

    payload = {
        "campaign": campaign,
        "batch_size_audio": batch_size_audio,
    }

    LOGGER.info("Triggering audio pipeline: campaign=%s, batch_size=%d", campaign, batch_size_audio)

    # Get state machine ARN from environment or use name
    sm_arn = os.environ.get("MEDIA_PIPELINES_AUDIO_STATE_MACHINE_ARN")
    sm_name = sm_arn if sm_arn else "media-pipelines-audio-pipeline"

    # In production, this would be triggered by EventBridge
    # For now, we trigger Step Functions directly
    result = trigger_state_machine(
        name=sm_name,
        payload=payload,
        aws_config=aws_config,
    )

    return result


def trigger_video_pipeline(campaign: str, batch_size_video: int) -> dict:
    """Trigger video pipeline execution."""
    import os

    runtime_config = get_runtime_config()
    aws_config = runtime_config.aws

    payload = {
        "campaign": campaign,
        "batch_size_video": batch_size_video,
    }

    LOGGER.info("Triggering video pipeline: campaign=%s, batch_size=%d", campaign, batch_size_video)

    # Get state machine ARN from environment or use name
    sm_arn = os.environ.get("MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN")
    sm_name = sm_arn if sm_arn else "media-pipelines-video-pipeline"

    result = trigger_state_machine(
        name=sm_name,
        payload=payload,
        aws_config=aws_config,
    )

    return result


def main():
    """Main entry point for scheduled trigger simulation."""
    if len(sys.argv) < 2:
        print("Usage: python schedule_trigger.py <audio|video|both> [campaign] [batch_size]")
        sys.exit(1)

    pipeline_type = sys.argv[1].lower()
    campaign = sys.argv[2] if len(sys.argv) > 2 else "nature"
    batch_size = int(sys.argv[3]) if len(sys.argv) > 3 else (5 if pipeline_type == "audio" else 2)

    try:
        if pipeline_type == "audio":
            result = trigger_audio_pipeline(campaign, batch_size)
            print(json.dumps(result, indent=2))
        elif pipeline_type == "video":
            result = trigger_video_pipeline(campaign, batch_size)
            print(json.dumps(result, indent=2))
        elif pipeline_type == "both":
            audio_result = trigger_audio_pipeline(campaign, batch_size)
            video_result = trigger_video_pipeline(campaign, batch_size)
            print(json.dumps({"audio": audio_result, "video": video_result}, indent=2))
        else:
            print(f"Unknown pipeline type: {pipeline_type}")
            sys.exit(1)
    except Exception as e:
        LOGGER.error("Failed to trigger pipeline: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
