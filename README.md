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

## Usage

```bash
# Full pipeline
python main.py

# Dry run (generate assets, skip upload)
python main.py --dry-run

# Override topic
python main.py --topic "The Great Fire of London"
```
