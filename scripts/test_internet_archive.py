#!/usr/bin/env python3
"""Test Internet Archive API for audio search."""

import sys

import requests

BASE_URL = "https://archive.org/advancedsearch.php"


def search_audio(query: str, rows: int = 5) -> dict:
    """Search for audio files."""
    params = {
        "q": f"title:{query} AND mediatype:audio AND licenseurl:*creativecommons*",
        "fl": "identifier,title,creator,date,licenseurl,downloads",
        "output": "json",
        "rows": rows,
    }

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_metadata(identifier: str) -> dict:
    """Get detailed metadata for an item."""
    url = f"https://archive.org/metadata/{identifier}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ia_api.py <query> [rows]")
        sys.exit(1)

    query = sys.argv[1]
    rows = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"🔍 Searching for: {query}")
    print(f"📊 Requesting {rows} results\n")

    try:
        results = search_audio(query, rows=rows)
        docs = results.get("response", {}).get("docs", [])

        print(f"✅ Found {len(docs)} results:\n")

        for i, doc in enumerate(docs, 1):
            print(f"{i}. {doc.get('title', 'Unknown')}")
            print(f"   Identifier: {doc.get('identifier')}")
            print(f"   Creator: {doc.get('creator', 'Unknown')}")
            print(f"   License: {doc.get('licenseurl', 'Unknown')}")
            print(f"   Downloads: {doc.get('downloads', 0)}")
            print()

        # Get detailed metadata for first result
        if docs:
            print("📋 Getting detailed metadata for first result...")
            identifier = docs[0]["identifier"]
            metadata = get_metadata(identifier)

            print("\n📁 Files available:")
            files = metadata.get("files", [])
            audio_files = [
                f
                for f in files
                if f.get("format") in ["VBR MP3", "64Kbps MP3", "128Kbps MP3", "OGG VORBIS"]
            ]

            for f in audio_files[:5]:
                print(f"   - {f.get('name')} ({f.get('format')}, {f.get('size', 0)} bytes)")
                print(f"     URL: https://archive.org/download/{identifier}/{f.get('name')}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
