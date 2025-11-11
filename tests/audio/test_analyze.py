"""Tests for audio analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.client import BaseClient

from audio_pipeline.analyze import (
    AudioAnalysis,
    analyze_audio,
    analyze_audio_from_s3,
    process_audio_batch,
    save_analysis_to_s3,
)
from shared.config import AwsConfig


@pytest.fixture
def mock_audio_data():
    """Mock audio data (simulated WAV/MP3 bytes)."""
    return b"fake audio data for testing"


@pytest.fixture
def mock_s3_client():
    """Mock S3 client."""
    client = MagicMock(spec=BaseClient)
    client.get_object = MagicMock(
        return_value={"Body": MagicMock(read=MagicMock(return_value=b"fake audio"))}
    )
    client.put_object = MagicMock(return_value={"ETag": "test-etag"})
    return client


@pytest.fixture
def aws_config():
    """Test AWS configuration."""
    return AwsConfig(
        region="us-east-1",
        audio_bucket="test-audio-bucket",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )


@patch("audio_pipeline.analyze.LIBROSA_AVAILABLE", True)
@patch("audio_pipeline.analyze.librosa")
@patch("audio_pipeline.analyze.np")
def test_analyze_audio_with_librosa(
    mock_np,
    mock_librosa,
    mock_audio_data,
):
    """Test audio analysis using librosa."""
    # Mock librosa module
    mock_y = MagicMock()
    mock_y.ndim = 1
    mock_sr = 22050
    mock_librosa.load.return_value = (mock_y, mock_sr)
    mock_librosa.to_mono.return_value = mock_y
    mock_librosa.get_duration.return_value = 5.5
    mock_librosa.feature.rms.return_value = MagicMock()
    mock_librosa.feature.spectral_centroid.return_value = MagicMock()

    # Mock numpy
    mock_np.mean.side_effect = [0.2, 2500.0]  # First for RMS, second for centroid

    analysis = analyze_audio(mock_audio_data, requires_attribution=True)

    assert analysis.duration == 5.5
    assert analysis.rms_loudness == pytest.approx(0.2)
    assert analysis.is_voice is True
    assert analysis.requires_attribution is True
    assert analysis.sample_rate == 22050
    assert analysis.channels == 1


@patch("audio_pipeline.analyze.LIBROSA_AVAILABLE", True)
@patch("audio_pipeline.analyze.PYDUB_AVAILABLE", True)
@patch("audio_pipeline.analyze.librosa")
@patch("audio_pipeline.analyze.AudioSegment")
def test_analyze_audio_fallback_to_pydub(mock_audio_segment, mock_librosa, mock_audio_data):
    """Test audio analysis fallback to pydub when librosa fails."""
    mock_librosa.load.side_effect = Exception("librosa failed")

    mock_audio = MagicMock()
    mock_audio.__len__.return_value = 5500  # milliseconds
    mock_audio.rms = 0.15
    mock_audio.frame_rate = 44100
    mock_audio.channels = 2
    mock_audio_segment.from_file.return_value = mock_audio

    analysis = analyze_audio(mock_audio_data, requires_attribution=False)

    assert analysis.duration == pytest.approx(5.5)
    assert analysis.rms_loudness == 0.15
    assert analysis.is_voice is False
    assert analysis.requires_attribution is False
    assert analysis.sample_rate == 44100
    assert analysis.channels == 2


@patch("audio_pipeline.analyze.analyze_audio")
def test_analyze_audio_from_s3(mock_analyze, mock_s3_client, aws_config):
    """Test analyzing audio downloaded from S3."""
    mock_analysis = AudioAnalysis(
        duration=5.5,
        rms_loudness=0.2,
        is_voice=True,
        requires_attribution=True,
        sample_rate=22050,
        channels=1,
    )
    mock_analyze.return_value = mock_analysis

    analysis = analyze_audio_from_s3(
        bucket="test-bucket",
        key="test-key.mp3",
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    assert analysis == mock_analysis
    mock_s3_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test-key.mp3")


@patch("audio_pipeline.analyze.S3Storage")
def test_save_analysis_to_s3(mock_storage_class, mock_s3_client, aws_config):
    """Test saving analysis results to S3."""
    mock_storage = MagicMock()
    mock_storage_class.return_value = mock_storage

    analysis = AudioAnalysis(
        duration=5.5,
        rms_loudness=0.2,
        is_voice=True,
        requires_attribution=True,
        sample_rate=22050,
        channels=1,
    )

    save_analysis_to_s3(
        analysis=analysis,
        bucket="test-bucket",
        key="test-key.json",
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    mock_storage.upload_bytes.assert_called_once()
    call_args = mock_storage.upload_bytes.call_args
    assert call_args.kwargs["bucket"] == "test-bucket"
    assert call_args.kwargs["key"] == "test-key.json"
    assert call_args.kwargs["content_type"] == "application/json"


@patch("audio_pipeline.analyze.analyze_audio_from_s3")
@patch("audio_pipeline.analyze.save_analysis_to_s3")
def test_process_audio_batch(
    mock_save,
    mock_analyze,
    mock_s3_client,
    aws_config,
):
    """Test processing a batch of audio files."""
    mock_analysis = AudioAnalysis(
        duration=5.5,
        rms_loudness=0.2,
        is_voice=True,
        requires_attribution=True,
        sample_rate=22050,
        channels=1,
    )
    mock_analyze.return_value = mock_analysis

    metadata_list = [
        {
            "s3_key": "media-raw/audio/nature/20240101_120000/12345.mp3",
            "license": "cc-by",
        },
        {
            "s3_key": "media-raw/audio/nature/20240101_120000/67890.mp3",
            "license": "cc0",
        },
    ]

    results = process_audio_batch(
        campaign="nature",
        timestamp="20240101_120000",
        metadata_list=metadata_list,
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    assert len(results) == 2
    assert results[0]["s3_key"] == "media-raw/audio/nature/20240101_120000/12345.mp3"
    assert "processed_key" in results[0]
    assert "analysis" in results[0]
    assert mock_analyze.call_count == 2
    assert mock_save.call_count == 2


def test_process_audio_batch_empty_metadata(mock_s3_client, aws_config):
    """Test processing batch with empty metadata."""
    results = process_audio_batch(
        campaign="nature",
        timestamp="20240101_120000",
        metadata_list=[],
        s3_client=mock_s3_client,
        aws_config=aws_config,
    )

    assert len(results) == 0


def test_audio_analysis_dataclass():
    """Test AudioAnalysis dataclass."""
    analysis = AudioAnalysis(
        duration=5.5,
        rms_loudness=0.2,
        is_voice=True,
        requires_attribution=True,
        sample_rate=22050,
        channels=1,
        bitrate=128,
    )

    assert analysis.duration == 5.5
    assert analysis.rms_loudness == 0.2
    assert analysis.is_voice is True
    assert analysis.requires_attribution is True
    assert analysis.sample_rate == 22050
    assert analysis.channels == 1
    assert analysis.bitrate == 128
