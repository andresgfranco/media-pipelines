#!/usr/bin/env python3
"""Script to get Freesound API Access Token using OAuth2 Client Credentials flow."""

import os
import sys

import requests

FREESOUND_TOKEN_URL = "https://freesound.org/apiv2/oauth2/access_token/"


def get_access_token(client_id: str, client_secret: str) -> str:
    """Get OAuth2 access token from Freesound API."""
    response = requests.post(
        FREESOUND_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        sys.exit(1)

    token_data = response.json()
    return token_data["access_token"]


if __name__ == "__main__":
    # Read credentials from environment variables
    client_id = os.getenv("FREESOUND_CLIENT_ID")
    client_secret = os.getenv("FREESOUND_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ Error: Environment variables not configured")
        print("")
        print("Set environment variables:")
        print("  export FREESOUND_CLIENT_ID='your_client_id'")
        print("  export FREESOUND_CLIENT_SECRET='your_client_secret'")
        print("")
        print("Or run:")
        print(
            "  FREESOUND_CLIENT_ID='your_client_id' FREESOUND_CLIENT_SECRET='your_client_secret' python3 scripts/get_freesound_token.py"
        )
        sys.exit(1)

    print("🔑 Getting Freesound Access Token...")
    access_token = get_access_token(client_id, client_secret)
    print("✅ Access Token obtained:")
    print(f"\n{access_token}\n")
    print("💡 Copy this token to configure it in AWS Lambda as FREESOUND_API_KEY")
