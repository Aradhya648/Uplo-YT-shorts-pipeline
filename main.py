"""HistoryShorts — Automated YouTube Shorts Pipeline"""

import argparse
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("output")
USED_TOPICS_FILE = Path("topics_used.txt")


def generate_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def log(msg: str):
    print(f"[HistoryShorts] {msg}", flush=True)


def cleanup_old_outputs(max_age_days: int = 3):
    """Delete output run folders older than max_age_days to prevent disk bloat."""
    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0
    for run_dir in OUTPUT_DIR.iterdir():
        if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
            try:
                shutil.rmtree(run_dir)
                deleted += 1
            except Exception:
                pass
    if deleted:
        log(f"Cleaned up {deleted} old output folder(s)")


def main():
    parser = argparse.ArgumentParser(description="HistoryShorts pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Generate assets but skip upload")
    parser.add_argument("--topic", type=str, default=None, help="Override topic (title|hook|description)")
    parser.add_argument("--count", type=int, default=1, help="Number of Shorts to produce (default 1)")
    args = parser.parse_args()

    # Clean up old outputs before starting
    if OUTPUT_DIR.exists():
        cleanup_old_outputs()

    for i in range(args.count):
        if args.count > 1:
            log(f"--- Short {i+1}/{args.count} ---")
        success = run_pipeline(args.dry_run, args.topic)
        if not success and args.count > 1:
            log(f"Short {i+1} failed — continuing to next")

    log("All done.")


def run_pipeline(dry_run: bool = False, topic_override: str | None = None) -> bool:
    run_id = generate_run_id()
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    log(f"Run ID: {run_id}")
    log(f"Output: {run_dir}")
    log(f"Dry run: {dry_run}")

    # ── Stage 1: Topic ────────────────────────────────────────────────────────
    log("Stage 1/6: Fetching topic...")
    from pipeline.topic_fetcher import fetch_topic

    if topic_override:
        parts = topic_override.split("|")
        topic = {
            "title": parts[0].strip(),
            "hook": parts[1].strip() if len(parts) > 1 else parts[0].strip(),
            "description": parts[2].strip() if len(parts) > 2 else parts[0].strip(),
            "source": "manual",
        }
        log(f"Using manual topic: {topic['title']}")
    else:
        try:
            topic = fetch_topic(used_topics_file=USED_TOPICS_FILE)
        except Exception as e:
            log(f"ERROR in topic fetch: {e}")
            return False

    log(f"Topic: {topic.get('topic_title', topic.get('title', 'unknown'))}")

    # ── Stage 2: Script ───────────────────────────────────────────────────────
    log("Stage 2/6: Generating script...")
    from pipeline.script_generator import generate_script

    try:
        script = generate_script(topic, run_dir)
    except Exception as e:
        log(f"ERROR in script generation: {e}")
        return False

    log(f"Script: {len(script.get('scenes', []))} scenes, hook: {script.get('hook', '')[:60]}")

    # ── Stage 3: Voiceover ────────────────────────────────────────────────────
    log("Stage 3/6: Generating voiceover...")
    from pipeline.voiceover import generate_voiceover

    try:
        audio_path = generate_voiceover(script, run_dir)
    except Exception as e:
        log(f"ERROR in voiceover: {e}")
        return False

    log(f"Audio: {audio_path}")

    # ── Stage 4: Assets ───────────────────────────────────────────────────────
    log("Stage 4/6: Fetching visual assets...")
    from pipeline.asset_fetcher import fetch_assets

    try:
        assets = fetch_assets(script, run_dir)
    except Exception as e:
        log(f"ERROR in asset fetch: {e}")
        return False

    log(f"Assets: {len(assets)} scenes")

    # ── Stage 5: Captions ─────────────────────────────────────────────────────
    log("Stage 5/6: Generating captions...")
    from pipeline.caption_generator import generate_captions

    try:
        caption_path = generate_captions(audio_path, run_dir)
    except Exception as e:
        log(f"ERROR in caption generation: {e}")
        return False

    log(f"Captions: {caption_path}")

    # ── Stage 6: Assembly ─────────────────────────────────────────────────────
    log("Stage 6/6: Assembling video...")
    from pipeline.video_assembler import assemble_video

    final_path = run_dir / "final.mp4"
    try:
        assemble_video(
            script=script,
            voiceover_path=audio_path,
            captions_path=caption_path,
            assets_manifest=assets,
            scenes_dir=run_dir,
            output_path=final_path,
        )
    except Exception as e:
        log(f"ERROR in video assembly: {e}")
        return False

    if not final_path.exists():
        log("ERROR: final.mp4 was not created")
        return False

    size_mb = final_path.stat().st_size / (1024 * 1024)
    log(f"Video ready: {final_path} ({size_mb:.1f} MB)")

    # ── Upload (skip in dry-run) ───────────────────────────────────────────────
    if dry_run:
        log("DRY RUN — skipping upload. Video is at:")
        log(f"  {final_path.resolve()}")
        return True

    log("Uploading to YouTube...")
    from pipeline.uploader import upload_and_notify

    try:
        video_url = upload_and_notify(
            video_path=final_path,
            script=script,
            run_id=run_id,
        )
        log(f"Uploaded: {video_url}")
    except Exception as e:
        log(f"ERROR in upload: {e}")
        return False

    # Mark topic as used
    try:
        with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
            f.write(topic.get("title", "") + "\n")
    except Exception:
        pass

    return True


if __name__ == "__main__":
    main()
