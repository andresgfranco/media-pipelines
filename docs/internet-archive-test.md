# Testing Internet Archive API for Audio

## Overview

Internet Archive provides a search API that doesn't require authentication for basic searches. It has a large collection of Creative Commons audio files.

## API Endpoint

**Base URL:** `https://archive.org/advancedsearch.php`

## Parameters

- `q`: Query string (supports AND, OR, NOT operators)
- `fl`: Fields to return (comma-separated)
- `output`: Response format (`json`)
- `rows`: Number of results per page (max 10,000)
- `page`: Page number (starts at 1)

## Testing with curl

### 1. Basic Audio Search

Search for audio files with "nature" in the title:

```bash
curl -s "https://archive.org/advancedsearch.php?q=title:nature%20AND%20mediatype:audio&fl=identifier,title,creator,date,licenseurl,downloads&output=json&rows=5" | python3 -m json.tool
```

### 2. Creative Commons Audio Search

Search for Creative Commons licensed audio:

```bash
curl -s "https://archive.org/advancedsearch.php?q=title:nature%20AND%20mediatype:audio%20AND%20licenseurl:*creativecommons*&fl=identifier,title,creator,date,licenseurl,downloads&output=json&rows=5" | python3 -m json.tool
```

### 3. Search by Collection

Search in specific audio collections:

```bash
# Search in "opensource_audio" collection
curl -s "https://archive.org/advancedsearch.php?q=collection:opensource_audio%20AND%20title:nature&fl=identifier,title,creator,date,licenseurl&output=json&rows=5" | python3 -m json.tool
```

### 4. Get File Details

Once you have an `identifier`, get detailed metadata:

```bash
# Replace IDENTIFIER with actual identifier from search results
curl -s "https://archive.org/metadata/IDENTIFIER" | python3 -m json.tool
```

### 5. Download Audio File

Get direct download URL:

```bash
# Replace IDENTIFIER and FILENAME with actual values
curl -s "https://archive.org/metadata/IDENTIFIER" | python3 -c "import sys, json; data=json.load(sys.stdin); print([f['name'] for f in data.get('files', []) if f.get('format') in ['VBR MP3', '64Kbps MP3', '128Kbps MP3', 'OGG VORBIS']][:3])"
```

## Testing with Python Script

Create a test script:

```python
#!/usr/bin/env python3
"""Test Internet Archive API for audio search."""
import json
import sys
from urllib.parse import urlencode

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

            print(f"\n📁 Files available:")
            files = metadata.get("files", [])
            audio_files = [
                f for f in files
                if f.get("format") in ["VBR MP3", "64Kbps MP3", "128Kbps MP3", "OGG VORBIS"]
            ]

            for f in audio_files[:5]:
                print(f"   - {f.get('name')} ({f.get('format')}, {f.get('size', 0)} bytes)")
                print(f"     URL: https://archive.org/download/{identifier}/{f.get('name')}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
```

## Expected Response Format

```json
{
  "responseHeader": {
    "status": 0,
    "QTime": 123,
    "params": {...}
  },
  "response": {
    "numFound": 1234,
    "start": 0,
    "docs": [
      {
        "identifier": "unique_id",
        "title": "Audio Title",
        "creator": "Artist Name",
        "date": "2020-01-01",
        "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
        "downloads": 1234
      }
    ]
  }
}
```

## Notes

1. **No API Key Required**: Basic searches don't require authentication
2. **Rate Limits**: Be respectful, don't spam requests
3. **File Formats**: Look for files with format "VBR MP3", "128Kbps MP3", "OGG VORBIS"
4. **Download URLs**: Format is `https://archive.org/download/{identifier}/{filename}`
5. **Creative Commons Filter**: Use `licenseurl:*creativecommons*` to filter CC licenses

## Next Steps

After testing:
1. Verify you can search for audio files
2. Verify you can get metadata
3. Verify you can construct download URLs
4. Then we'll implement it in the pipeline
