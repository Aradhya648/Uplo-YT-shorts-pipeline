"""
Visual Asset Fetcher — Downloads one visual asset per scene.

Fallback chain per scene:
1. Google AI Studio Veo (for scenes in google_ai_video_scenes config) → AI video
2. Pexels API → stock video clip (portrait/vertical preferred)
3. Pollinations.ai → AI-generated image (fallback)

All assets saved to output/{run_id}/scenes/
"""

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GOOGLE_AI_STUDIO_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY")

# Load config
_config_path = Path(__file__).parent.parent / "config.yaml"
if _config_path.exists():
    with open(_config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {}

GOOGLE_AI_VIDEO_SCENES = CONFIG.get("assets", {}).get("google_ai_video_scenes", [0, 3])

UA = {"User-Agent": "HistoryShorts/1.0"}


def _download_file(url: str, output_path: Path, headers: dict | None = None) -> bool:
    """Download a file with proper headers."""
    h = {**UA, **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as resp:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.read())
    return True


def fetch_pexels_video(search_query: str, output_path: Path) -> bool:
    """Download a portrait video clip from Pexels."""
    if not PEXELS_API_KEY:
        print("[Assets] No Pexels API key, skipping")
        return False

    encoded_query = urllib.parse.quote(search_query)
    url = f"https://api.pexels.com/videos/search?query={encoded_query}&per_page=5&orientation=portrait"

    try:
        req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY, **UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        videos = data.get("videos", [])
        if not videos:
            print(f"[Assets] Pexels: no results for '{search_query}'")
            return False

        # Pick best video: prefer 720p+ portrait files
        best_file = None
        for video in videos:
            for vf in video.get("video_files", []):
                w = vf.get("width", 0)
                h = vf.get("height", 0)
                # Prefer portrait (h > w) and at least 720p wide
                if h > w and w >= 720:
                    best_file = vf
                    break
                elif w >= 720 and not best_file:
                    best_file = vf
            if best_file and best_file.get("height", 0) > best_file.get("width", 0):
                break

        if not best_file:
            # Fall back to any available file
            for video in videos:
                if video.get("video_files"):
                    best_file = video["video_files"][0]
                    break

        if not best_file:
            return False

        download_url = best_file["link"]
        print(f"[Assets] Pexels: downloading {best_file.get('width')}x{best_file.get('height')} clip")

        _download_file(download_url, output_path)
        print(f"[Assets] Pexels: saved {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
        return True

    except Exception as e:
        print(f"[Assets] Pexels failed for '{search_query}': {e}")
        return False


def fetch_pollinations_image(visual_prompt: str, output_path: Path) -> bool:
    """Generate and download an AI image from Pollinations.ai."""
    encoded_prompt = urllib.parse.quote(visual_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"

    try:
        print(f"[Assets] Pollinations: generating image...")
        _download_file(url, output_path)

        file_size = output_path.stat().st_size
        if file_size < 5000:
            print(f"[Assets] Pollinations: file too small ({file_size}B), likely error")
            output_path.unlink(missing_ok=True)
            return False

        print(f"[Assets] Pollinations: saved {output_path} ({file_size / 1024:.0f} KB)")
        return True

    except Exception as e:
        print(f"[Assets] Pollinations failed: {e}")
        return False


def fetch_google_ai_video(visual_prompt: str, output_path: Path, duration: int = 5) -> bool:
    """Generate a video clip using Google AI Studio Veo."""
    if not GOOGLE_AI_STUDIO_API_KEY:
        print("[Assets] No Google AI Studio key, skipping")
        return False

    model = "veo-2.0-generate-001"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predictLongRunning?key={GOOGLE_AI_STUDIO_API_KEY}"

    payload = json.dumps({
        "instances": [{"prompt": visual_prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "9:16",
            "durationSeconds": duration,
            "personGeneration": "allow_adult",
        },
    })

    try:
        # Step 1: Submit generation request
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        operation_name = data.get("name")
        if not operation_name:
            print(f"[Assets] Veo: no operation name in response")
            return False

        print(f"[Assets] Veo: submitted, operation={operation_name}")

        # Step 2: Poll for completion (max 120 seconds)
        poll_url = f"https://generativelanguage.googleapis.com/v1beta/{operation_name}?key={GOOGLE_AI_STUDIO_API_KEY}"
        max_polls = 24
        for i in range(max_polls):
            time.sleep(5)
            poll_req = urllib.request.Request(poll_url)
            with urllib.request.urlopen(poll_req, timeout=15) as resp:
                result = json.loads(resp.read().decode())

            if result.get("done"):
                break
            print(f"[Assets] Veo: still processing... ({(i + 1) * 5}s)")
        else:
            print("[Assets] Veo: timed out after 120s")
            return False

        # Step 3: Extract video URI and download
        response = result.get("response", {})
        samples = response.get("generateVideoResponse", {}).get("generatedSamples", [])
        if not samples:
            print(f"[Assets] Veo: no samples in response")
            return False

        video_uri = samples[0].get("video", {}).get("uri", "")
        if not video_uri:
            print("[Assets] Veo: no video URI")
            return False

        # Download video (must follow redirects, append key)
        download_url = f"{video_uri}&key={GOOGLE_AI_STUDIO_API_KEY}" if "?" in video_uri else f"{video_uri}?key={GOOGLE_AI_STUDIO_API_KEY}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[Assets] Veo: downloading video...")
        dl_req = urllib.request.Request(download_url)
        with urllib.request.urlopen(dl_req, timeout=60) as resp:
            # Follow redirects manually if needed
            video_data = resp.read()

        output_path.write_bytes(video_data)
        print(f"[Assets] Veo: saved {output_path} ({len(video_data) / 1024:.0f} KB)")
        return True

    except Exception as e:
        print(f"[Assets] Veo failed: {e}")
        return False


def fetch_assets(script: dict, output_dir: Path) -> list[dict]:
    """Fetch one visual asset per scene using the fallback chain."""
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    assets = []
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        visual_prompt = scene.get("visual_prompt", "")
        pexels_search = scene.get("pexels_search", "")

        print(f"\n[Assets] === Scene {scene_num} ===")
        print(f"[Assets] Visual: {visual_prompt[:60]}...")

        asset_info = {"scene_number": scene_num, "type": None, "path": None}

        # Try Google AI Video for configured scenes
        if scene_num - 1 in GOOGLE_AI_VIDEO_SCENES:
            video_path = scenes_dir / f"scene_{scene_num}_veo.mp4"
            if fetch_google_ai_video(visual_prompt, video_path):
                asset_info["type"] = "veo_video"
                asset_info["path"] = str(video_path)
                assets.append(asset_info)
                continue

        # Try Pexels stock footage
        if pexels_search:
            video_path = scenes_dir / f"scene_{scene_num}_pexels.mp4"
            if fetch_pexels_video(pexels_search, video_path):
                asset_info["type"] = "pexels_video"
                asset_info["path"] = str(video_path)
                assets.append(asset_info)
                continue

        # Fallback: Pollinations AI image
        image_path = scenes_dir / f"scene_{scene_num}_pollinations.jpg"
        if fetch_pollinations_image(visual_prompt, image_path):
            asset_info["type"] = "pollinations_image"
            asset_info["path"] = str(image_path)
            assets.append(asset_info)
            continue

        print(f"[Assets] WARNING: No asset fetched for scene {scene_num}")
        assets.append(asset_info)

    # Save asset manifest
    manifest_path = output_dir / "assets.json"
    manifest_path.write_text(json.dumps(assets, indent=2))
    print(f"\n[Assets] Manifest saved: {manifest_path}")

    fetched = sum(1 for a in assets if a["path"])
    total = len(assets)
    print(f"[Assets] Fetched {fetched}/{total} assets")

    return assets


if __name__ == "__main__":
    # Standalone test: load script.json and fetch assets
    test_script_path = Path("output/test_gemma/script.json")
    if not test_script_path.exists():
        test_script_path = Path("output/test_script/script.json")
    if not test_script_path.exists():
        print("No test script found. Run script_generator.py first.")
        raise SystemExit(1)

    script = json.loads(test_script_path.read_text())
    output_dir = Path("output/test_assets")
    assets = fetch_assets(script, output_dir)

    print("\n" + "=" * 60)
    print("ASSET SUMMARY")
    print("=" * 60)
    for a in assets:
        status = "OK" if a["path"] else "MISSING"
        print(f"  Scene {a['scene_number']}: [{status}] {a['type'] or 'none'} — {a.get('path', 'n/a')}")
