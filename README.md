# HistoryShorts

Fully automated YouTube Shorts pipeline for historical facts and micro-history content.

## Setup

**Requirements:** Python 3.10+

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install FFmpeg (if not already on PATH):
   ```bash
   # Windows
   winget install Gyan.FFmpeg
   # macOS
   brew install ffmpeg
   # Linux
   sudo apt install ffmpeg
   ```

4. Copy `.env.example` to `.env` and fill in API keys:
   ```bash
   cp .env.example .env
   ```

5. Always use `--dry-run` during testing (skips upload, Sheets, and Telegram):
   ```bash
   python main.py --dry-run
   ```

## YouTube OAuth Setup

You need a refresh token once per Google account. This is separate from the API key.

**Prerequisites:** A Google Cloud project with the YouTube Data API v3 enabled and an OAuth 2.0 "Desktop app" client ID created. Download the client ID and secret from the Google Cloud Console.

**Steps:**

1. Add your client credentials to `.env`:
   ```
   YOUTUBE_CLIENT_ID=your_client_id_here
   YOUTUBE_CLIENT_SECRET=your_client_secret_here
   ```

2. Run the token script:
   ```bash
   python get_refresh_token.py
   ```

3. A browser window will open — sign in with the YouTube channel's Google account and click **Allow**.

4. The terminal will print a line like:
   ```
   YOUTUBE_REFRESH_TOKEN=1//0gxxxxxxxxxxxxxxx...
   ```

5. Paste that line into your `.env` file. That's it — the token doesn't expire unless you revoke access.

## Usage

```bash
# Full pipeline
python main.py

# Dry run (generate assets, skip upload)
python main.py --dry-run

# Override topic
python main.py --topic "The Great Fire of London"
```
