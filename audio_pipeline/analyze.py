"""Audio analysis using librosa and pydub."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from io import BytesIO

try:
    import librosa
    import numpy as np

    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    librosa = None
    np = None

try:
    from pydub import AudioSegment

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None

from botocore.client import BaseClient

from shared.aws import S3Storage, invoke_with_retry
from shared.config import AwsConfig, get_runtime_config

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AudioAnalysis:
    """Audio analysis results."""

    duration: float
    rms_loudness: float
    is_voice: bool
    requires_attribution: bool
    sample_rate: int
    channels: int
    bitrate: int | None = None


def analyze_audio(
    audio_data: bytes,
    *,
    requires_attribution: bool = True,
) -> AudioAnalysis:
    """Analyze audio file and extract features."""
    audio_bytes = BytesIO(audio_data)

    # Load with librosa for analysis if available
    if LIBROSA_AVAILABLE:
        try:
            y, sr = librosa.load(audio_bytes, sr=None, mono=False)
            if y.ndim > 1:
                y_mono = librosa.to_mono(y)
                channels = y.shape[0]
            else:
                y_mono = y
                channels = 1

            duration = librosa.get_duration(y=y_mono, sr=sr)
            rms = librosa.feature.rms(y=y_mono)[0]
            rms_loudness = float(np.mean(rms))

            # Simple heuristic: voice detection based on spectral centroid
            spectral_centroids = librosa.feature.spectral_centroid(y=y_mono, sr=sr)[0]
            avg_centroid = float(np.mean(spectral_centroids))
            # Human voice typically has spectral centroid between 1000-4000 Hz
            is_voice = 1000 <= avg_centroid <= 4000

        except Exception as e:
            LOGGER.warning("librosa analysis failed, falling back to pydub: %s", e)
            # Fallback to pydub for basic analysis
            audio_bytes.seek(0)
            if not PYDUB_AVAILABLE:
                raise RuntimeError("Neither librosa nor pydub available") from e
            audio = AudioSegment.from_file(audio_bytes)
            duration = len(audio) / 1000.0  # pydub returns milliseconds
            rms_loudness = audio.rms
            is_voice = False  # Can't determine with pydub alone
            sr = audio.frame_rate
            channels = audio.channels
    elif PYDUB_AVAILABLE:
        # Fallback to pydub for basic analysis
        audio = AudioSegment.from_file(audio_bytes)
        duration = len(audio) / 1000.0  # pydub returns milliseconds
        rms_loudness = audio.rms
        is_voice = False  # Can't determine with pydub alone
        sr = audio.frame_rate
        channels = audio.channels
    else:
        raise RuntimeError("Neither librosa nor pydub available for audio analysis")

    return AudioAnalysis(
        duration=duration,
        rms_loudness=rms_loudness,
        is_voice=is_voice,
        requires_attribution=requires_attribution,
        sample_rate=sr,
        channels=channels,
        bitrate=None,
    )


def analyze_audio_from_s3(
    *,
    bucket: str,
    key: str,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
    requires_attribution: bool = True,
) -> AudioAnalysis:
    """Download audio from S3 and analyze it."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    def _get_object() -> dict:
        return s3_client.get_object(Bucket=bucket, Key=key)

    response = invoke_with_retry(_get_object)
    audio_data = response["Body"].read()

    return analyze_audio(audio_data, requires_attribution=requires_attribution)


def save_analysis_to_s3(
    *,
    analysis: AudioAnalysis,
    bucket: str,
    key: str,
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> None:
    """Save analysis results as JSON to S3."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    storage = S3Storage(s3_client)
    analysis_dict = asdict(analysis)
    json_data = json.dumps(analysis_dict, indent=2).encode("utf-8")

    storage.upload_bytes(
        bucket=bucket,
        key=key,
        data=json_data,
        content_type="application/json",
    )


def process_audio_batch(
    *,
    campaign: str,
    timestamp: str,
    metadata_list: list[dict],
    s3_client: BaseClient | None = None,
    aws_config: AwsConfig | None = None,
) -> list[dict]:
    """Process a batch of ingested audio files."""
    if aws_config is None:
        runtime_config = get_runtime_config()
        aws_config = runtime_config.aws

    if s3_client is None:
        from shared.aws import build_aws_resources

        resources = build_aws_resources(aws_config=aws_config)
        s3_client = resources["s3"]

    results = []

    for metadata in metadata_list:
        s3_key = metadata.get("s3_key", "")
        if not s3_key:
            LOGGER.warning("Missing s3_key in metadata, skipping")
            continue

        try:
            LOGGER.info("Analyzing audio: %s", s3_key)
            analysis = analyze_audio_from_s3(
                bucket=aws_config.audio_bucket,
                key=s3_key,
                s3_client=s3_client,
                aws_config=aws_config,
                requires_attribution=metadata.get("license", "") != "cc0",
            )

            # Save analysis to processed bucket
            processed_key = s3_key.replace("media-raw", "media-processed").replace(
                ".mp3", "_summary.json"
            )
            save_analysis_to_s3(
                analysis=analysis,
                bucket=aws_config.audio_bucket,
                key=processed_key,
                s3_client=s3_client,
                aws_config=aws_config,
            )

            result = {
                "s3_key": s3_key,
                "processed_key": processed_key,
                "analysis": asdict(analysis),
            }
            results.append(result)

        except Exception as e:
            LOGGER.error("Failed to analyze audio %s: %s", s3_key, e, exc_info=True)
            continue

    LOGGER.info("Processed %d audio files for campaign: %s", len(results), campaign)
    return results
