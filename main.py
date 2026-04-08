"""HistoryShorts — Automated YouTube Shorts Pipeline"""

import argparse
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("output")


def generate_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


def main():
    parser = argparse.ArgumentParser(description="HistoryShorts pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Generate assets but skip upload")
    parser.add_argument("--topic", type=str, default=None, help="Override topic selection")
    args = parser.parse_args()

    run_id = generate_run_id()
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[HistoryShorts] Run ID: {run_id}")
    print(f"[HistoryShorts] Output: {run_dir}")
    print(f"[HistoryShorts] Dry run: {args.dry_run}")

    # Pipeline stages will be added in subsequent milestones
    print("[HistoryShorts] Pipeline scaffold ready. Stages coming in M2+.")


if __name__ == "__main__":
    main()
