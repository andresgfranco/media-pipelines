#!/usr/bin/env python3
"""Manual test of audio ingestion with Internet Archive."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

from botocore.client import BaseClient

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from audio_pipeline.ingest import InternetArchiveClient, ingest_audio_batch  # noqa: E402
from shared.config import AwsConfig, set_runtime_config  # noqa: E402


def test_internet_archive_client():
    """Test Internet Archive client directly."""
    print("=" * 60)
    print("Testing Internet Archive Client")
    print("=" * 60)

    client = InternetArchiveClient()

    # Test search
    print("\n1. Testing search...")
    results = client.search("nature", rows=3)
    print(f"   ✅ Found {len(results)} results")

    if results:
        for i, item in enumerate(results[:3], 1):
            print(f"   {i}. {item.get('title', 'Unknown')}")
            print(f"      ID: {item.get('identifier')}")
            print(f"      Creator: {item.get('creator', 'Unknown')}")

    # Test metadata retrieval
    if results:
        print("\n2. Testing metadata retrieval...")
        identifier = results[0]["identifier"]
        metadata = client.get_metadata(identifier)
        files = metadata.get("files", [])
        print(f"   ✅ Retrieved metadata for {identifier}")
        print(f"   ✅ Found {len(files)} files")

        # Test file selection
        print("\n3. Testing file selection...")
        selected = client.select_audio_file(files)
        if selected:
            print(f"   ✅ Selected file: {selected.get('name')}")
            print(f"      Format: {selected.get('format')}")
            print(f"      Duration: {selected.get('length')}s")
            print(f"      Size: {selected.get('size')} bytes")
        else:
            print("   ⚠️  No suitable file found")

    print("\n" + "=" * 60)
    return results


def test_ingest_with_mock_s3():
    """Test ingestion with mocked S3."""
    print("\n" + "=" * 60)
    print("Testing Audio Ingestion (with mocked S3)")
    print("=" * 60)

    # Set up mock AWS config
    aws_config = AwsConfig(
        region="us-east-1",
        audio_bucket="test-bucket",
        video_bucket="test-video-bucket",
        metadata_table="test-metadata-table",
    )

    set_runtime_config(
        environment="test",
        audio_bucket=aws_config.audio_bucket,
        video_bucket=aws_config.video_bucket,
        metadata_table=aws_config.metadata_table,
        region=aws_config.region,
    )

    # Create mock S3 client
    mock_s3_client = MagicMock(spec=BaseClient)
    mock_s3_client.put_object = MagicMock(return_value={"ETag": "test-etag"})

    print("\n1. Running ingest_audio_batch (batch_size=3)...")
    print("   This will make real API calls to Internet Archive")
    print("   but upload to mocked S3")
    print("   Trying multiple queries to find files in duration range...")

    # Try multiple campaigns to find files that fit our duration criteria
    campaigns_to_try = ["sound effects", "nature", "ocean"]
    metadata_list = []

    for campaign in campaigns_to_try:
        if len(metadata_list) > 0:
            break
        print(f"\n   Trying campaign: {campaign}")
        try:
            metadata_list = ingest_audio_batch(
                campaign=campaign,
                batch_size=3,
                s3_client=mock_s3_client,
                aws_config=aws_config,
            )
            if metadata_list:
                print(f"   ✅ Found {len(metadata_list)} files with campaign '{campaign}'")
                break
        except Exception as e:
            print(f"   ⚠️  Error with campaign '{campaign}': {e}")
            continue

    try:
        print("\n   ✅ Ingestion completed!")
        print(f"   ✅ Processed {len(metadata_list)} files")

        if metadata_list:
            m = metadata_list[0]
            print("\n   File details:")
            print(f"   - Archive ID: {m.archive_id}")
            print(f"   - Title: {m.title}")
            print(f"   - Author: {m.author}")
            print(f"   - Duration: {m.duration}s")
            print(f"   - File Size: {m.file_size} bytes")
            print(f"   - License: {m.license}")
            print(f"   - S3 Key: {m.s3_key}")

            # Verify S3 was called
            assert mock_s3_client.put_object.called, "S3 upload should have been called"
            print("\n   ✅ S3 upload was called (mocked)")

        return True

    except Exception as e:
        print(f"\n   ❌ Error during ingestion: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🧪 Manual Test of Audio Ingestion Pipeline")
    print("=" * 60)

    # Test 1: Client functionality
    results = test_internet_archive_client()

    if not results:
        print("\n❌ No search results found. Cannot proceed with ingestion test.")
        sys.exit(1)

    # Test 2: Full ingestion (with mocked S3)
    success = test_ingest_with_mock_s3()

    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ Tests failed")
        print("=" * 60)
        sys.exit(1)
