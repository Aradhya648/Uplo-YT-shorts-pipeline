"""
download_bgm.py — Download a free royalty-free background music track.

Places the file at assets/bgm/bgm.mp3 for use in the HistoryShorts pipeline.
Run once from the project root:  python download_bgm.py
"""

import urllib.request
import sys
from pathlib import Path

BGM_OUT = Path("assets/bgm/bgm.mp3")

# Royalty-free tracks from Pixabay (license: free for commercial use, no attribution required)
# Multiple fallbacks in case one URL goes stale
CANDIDATES = [
    # Epic/cinematic history-style tracks from Pixabay CDN
    ("Epic Cinematic", "https://cdn.pixabay.com/audio/2023/10/28/audio_9f57de9374.mp3"),
    ("Dramatic History", "https://cdn.pixabay.com/audio/2022/10/25/audio_fbd38e2c8d.mp3"),
    ("Ancient Mystery",  "https://cdn.pixabay.com/audio/2023/02/28/audio_9dc88be02f.mp3"),
    ("Dark Ambient",     "https://cdn.pixabay.com/audio/2022/11/22/audio_febc508520.mp3"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HistoryShorts-Pipeline/1.0)"}


def try_download(name: str, url: str, out: Path) -> bool:
    print(f"  Trying: {name}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 50_000:  # less than 50 KB is likely an error page
            print(f"    Too small ({len(data)} bytes) — skipping")
            return False
        out.write_bytes(data)
        print(f"    Saved: {out} ({len(data) / 1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"    Failed: {e}")
        return False


def main():
    BGM_OUT.parent.mkdir(parents=True, exist_ok=True)

    if BGM_OUT.exists() and BGM_OUT.stat().st_size > 50_000:
        print(f"BGM already exists: {BGM_OUT} ({BGM_OUT.stat().st_size / 1024:.0f} KB)")
        print("Delete it first if you want to re-download.")
        return

    print("Downloading background music for HistoryShorts pipeline...")
    for name, url in CANDIDATES:
        if try_download(name, url, BGM_OUT):
            print(f"\nBGM ready: {BGM_OUT}")
            print("The pipeline will now automatically mix this under every video.")
            return

    print("\nAll download attempts failed.")
    print("Please manually download an MP3 and save it to: assets/bgm/bgm.mp3")
    print("See assets/bgm/README.txt for free sources.")
    sys.exit(1)


if __name__ == "__main__":
    main()
