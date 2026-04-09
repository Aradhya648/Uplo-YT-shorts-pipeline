"""
YouTube Uploader — Uploads final video with metadata.

Also logs to Google Sheets and sends Telegram notification.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

import yaml
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_config_path = Path(__file__).parent.parent / "config.yaml"
if _config_path.exists():
    with open(_config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {}

UPLOAD_CONFIG = CONFIG.get("upload", {})


def _get_youtube_client():
    """Build authenticated YouTube API client."""
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def build_metadata(script: dict) -> dict:
    """Build YouTube video metadata from script."""
    title_template = UPLOAD_CONFIG.get("title_template", "{hook} #Shorts")
    desc_template = UPLOAD_CONFIG.get("description_template", "{summary}\n\n#{topic_tag}")
    tags = UPLOAD_CONFIG.get("tags", ["history", "shorts", "historyfacts"])
    category_id = UPLOAD_CONFIG.get("category_id", "27")
    privacy = UPLOAD_CONFIG.get("privacy", "public")

    hook = script.get("hook", "")
    summary = script.get("summary", "")
    topic_tag = script.get("topic_tag", "history").replace("#", "")

    title = title_template.format(hook=hook, summary=summary, topic_tag=topic_tag)
    # Truncate title to 100 chars (YouTube limit)
    if len(title) > 100:
        title = title[:97] + "..."

    description = desc_template.format(
        hook=hook,
        summary=summary,
        topic_tag=topic_tag,
    )

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags + [topic_tag],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }


def upload_video(video_path: Path, script: dict) -> str:
    """Upload video to YouTube, return video URL."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    print(f"[Uploader] Authenticating with YouTube...")
    youtube = _get_youtube_client()

    metadata = build_metadata(script)
    print(f"[Uploader] Title: {metadata['snippet']['title']}")
    print(f"[Uploader] Privacy: {metadata['status']['privacyStatus']}")

    print(f"[Uploader] Uploading {video_path.name} ({video_path.stat().st_size / (1024*1024):.1f} MB)...")

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,  # 1MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=metadata,
        media_body=media,
    )

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"[Uploader] Upload progress: {progress}%")
        except Exception as e:
            retry += 1
            if retry > 3:
                raise RuntimeError(f"Upload failed after 3 retries: {e}")
            print(f"[Uploader] Chunk error, retrying ({retry}/3): {e}")
            time.sleep(5)

    video_id = response["id"]
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"[Uploader] Uploaded: {video_url}")

    return video_url


def log_to_sheets(run_id: str, topic: str, title: str, video_url: str, status: str = "SUCCESS"):
    """Log upload to Google Sheets."""
    import gspread

    key_file = os.path.expanduser(os.getenv("GOOGLE_SHEETS_KEY_FILE", "~/drut-sheets-key.json"))
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "")

    if not Path(key_file).exists() or not sheet_id:
        print(f"[Uploader] Sheets: key file or sheet ID missing, skipping")
        return

    try:
        from google.oauth2.service_account import Credentials as SACredentials
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = SACredentials.from_service_account_file(key_file, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1

        from datetime import datetime
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            run_id,
            topic,
            title,
            video_url,
            status,
        ]
        sheet.append_row(row)
        print(f"[Uploader] Logged to Sheets: {row}")
    except Exception as e:
        print(f"[Uploader] Sheets logging failed: {e}")


def send_telegram(message: str):
    """Send Telegram notification via DRUT bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Uploader] Telegram: no token/chat_id, skipping")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    })

    try:
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print(f"[Uploader] Telegram sent")
            else:
                print(f"[Uploader] Telegram failed: {result}")
    except Exception as e:
        print(f"[Uploader] Telegram error: {e}")


def upload_and_notify(
    video_path: Path,
    script: dict,
    run_id: str,
    dry_run: bool = False,
) -> str:
    """Upload video, log to Sheets, send Telegram. Returns video URL."""
    topic_title = script.get("title", "Unknown")

    if dry_run:
        fake_url = f"https://www.youtube.com/shorts/DRY_RUN_{run_id}"
        print(f"[Uploader] DRY RUN — skipping upload. Fake URL: {fake_url}")
        return fake_url

    # Upload
    video_url = upload_video(video_path, script)

    # Log to Sheets
    metadata = build_metadata(script)
    title = metadata["snippet"]["title"]
    log_to_sheets(run_id, topic_title, title, video_url, "SUCCESS")

    # Telegram notification
    message = (
        f"<b>Buried | New Short Published</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Topic:</b> {topic_title}\n"
        f"<b>URL:</b> {video_url}\n"
        f"<b>Run ID:</b> {run_id}"
    )
    send_telegram(message)

    return video_url


if __name__ == "__main__":
    # Standalone test: upload test video
    test_video = Path("output/test_gemma/final.mp4")
    if not test_video.exists():
        print("No final.mp4 found. Run video_assembler.py first.")
        raise SystemExit(1)

    script_path = Path("output/test_gemma/script.json")
    script = json.loads(script_path.read_text())

    url = upload_and_notify(test_video, script, run_id="test_001", dry_run=False)
    print(f"\nVideo live at: {url}")
