# HistoryShorts

Fully automated YouTube Shorts pipeline for historical facts and micro-history content.

## Setup

1. Install Python dependencies: `pip install -r requirements.txt`
2. Install FFmpeg: `winget install Gyan.FFmpeg`
3. Download Piper TTS model to `assets/piper-models/`
4. Copy `.env.example` to `.env` and fill in API keys
5. Run: `python main.py`

## Usage

```bash
# Full pipeline
python main.py

# Dry run (generate assets, skip upload)
python main.py --dry-run

# Override topic
python main.py --topic "The Great Fire of London"
```
