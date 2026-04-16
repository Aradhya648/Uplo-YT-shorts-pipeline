"""
get_refresh_token.py — One-time script to obtain a YouTube OAuth refresh token.

Run this once to generate the YOUTUBE_REFRESH_TOKEN value for your .env file.
A browser window will open asking you to authorise the app with your Google account.

Usage:
    python get_refresh_token.py
"""

import os
import sys

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "ERROR: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env\n"
            "Copy .env.example to .env and fill in both values first."
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    print("\n" + "=" * 60)
    print("SUCCESS — copy this line into your .env file:")
    print("=" * 60)
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    print("=" * 60)


if __name__ == "__main__":
    main()
