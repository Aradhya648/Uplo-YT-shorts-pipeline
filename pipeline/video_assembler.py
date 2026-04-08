"""
Video Assembler — Combines all assets into a final 9:16 YouTube Short.

Process:
1. Load scene assets (videos or images)
2. Crop/resize to 1080x1920
3. For images: apply Ken Burns zoom effect via FFmpeg
4. Trim/extend clips to match scene duration
5. Concatenate all scenes
6. Overlay voiceover audio
7. Burn captions from SRT via FFmpeg
8. Export final MP4
"""

import json
import subprocess
from pathlib import Path

from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
import yaml
from dotenv import load_dotenv

load_dotenv()

_config_path = Path(__file__).parent.parent / "config.yaml"
if _config_path.exists():
    with open(_config_path) as f:
        CONFIG = yaml.safe_load(f)
else:
    CONFIG = {}

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30

FFMPEG_DIR = None
for p in [
    Path("C:/Users/91979/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin"),
]:
    if p.exists():
        FFMPEG_DIR = p
        break


def _get_ffmpeg() -> str:
    return str(FFMPEG_DIR / "ffmpeg.exe") if FFMPEG_DIR else "ffmpeg"


def _get_ffprobe() -> str:
    return str(FFMPEG_DIR / "ffprobe.exe") if FFMPEG_DIR else "ffprobe"


def _crop_resize_video(input_path: Path, output_path: Path, duration: float) -> bool:
    """Use FFmpeg to crop, resize, and trim a video to 1080x1920."""
    ffmpeg = _get_ffmpeg()

    # FFmpeg filter: crop to 9:16 center, scale to 1080x1920, trim to duration
    # crop=w:h:x:y — if wider than 9:16, crop width; if taller, crop height
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", vf,
        "-r", str(TARGET_FPS),
        "-c:v", "libx264", "-preset", "fast",
        "-an",  # no audio from scene clips
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[Assembly] FFmpeg crop/resize failed: {result.stderr[:300]}")
        return False
    return True


def _image_to_kenburns_video(input_path: Path, output_path: Path, duration: float) -> bool:
    """Use FFmpeg to create a Ken Burns zoom video from a static image."""
    ffmpeg = _get_ffmpeg()

    # Ken Burns: slow zoom from 100% to 130% over duration, centered
    # zoompan filter: z='1+0.3*on/({duration}*{fps})' means zoom from 1.0 to 1.3
    total_frames = int(duration * TARGET_FPS)
    vf = (
        f"zoompan=z='1+0.3*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=1080x1920:fps={TARGET_FPS},"
        f"setsar=1"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[Assembly] FFmpeg Ken Burns failed: {result.stderr[:300]}")
        return False
    return True


def _loop_video(input_path: Path, output_path: Path, duration: float) -> bool:
    """Loop a short video to reach the target duration."""
    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-stream_loop", "-1",
        "-i", str(input_path),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast",
        "-an",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def prepare_scene_clip(asset_info: dict, scenes_dir: Path, duration: float, work_dir: Path) -> Path | None:
    """Prepare a single scene clip: crop, resize, trim/loop to exact duration."""
    if not asset_info.get("path"):
        return None

    asset_path = scenes_dir / Path(asset_info["path"]).name
    if not asset_path.exists():
        # Try the full path
        asset_path = Path(asset_info["path"])
    if not asset_path.exists():
        print(f"[Assembly] Asset not found: {asset_info['path']}")
        return None

    scene_num = asset_info["scene_number"]
    work_dir.mkdir(parents=True, exist_ok=True)

    is_image = asset_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']

    if is_image:
        # Ken Burns effect for images
        output = work_dir / f"scene_{scene_num}_ready.mp4"
        print(f"[Assembly] Scene {scene_num}: Ken Burns from image {asset_path.name}")
        if _image_to_kenburns_video(asset_path, output, duration):
            return output
        return None

    # Video clip — crop/resize
    cropped = work_dir / f"scene_{scene_num}_cropped.mp4"
    print(f"[Assembly] Scene {scene_num}: Crop/resize video {asset_path.name}")

    # Get video duration
    probe_cmd = [
        _get_ffprobe(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(asset_path),
    ]
    try:
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
        clip_duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        clip_duration = duration  # assume it's long enough

    print(f"[Assembly] Scene {scene_num}: source={asset_path.name} ({clip_duration:.1f}s), need={duration}s")

    # Crop and resize, pass the full clip
    if not _crop_resize_video(asset_path, cropped, clip_duration):
        return None

    # If clip is shorter than needed, loop it
    if clip_duration < duration - 0.5:
        looped = work_dir / f"scene_{scene_num}_looped.mp4"
        if _loop_video(cropped, looped, duration):
            cropped.unlink(missing_ok=True)
            # Final trim
            ready = work_dir / f"scene_{scene_num}_ready.mp4"
            trim_cmd = [_get_ffmpeg(), "-y", "-i", str(looped), "-t", str(duration), "-c", "copy", str(ready)]
            subprocess.run(trim_cmd, capture_output=True, text=True, timeout=30)
            looped.unlink(missing_ok=True)
            return ready if ready.exists() else None
    else:
        # Trim to exact duration
        ready = work_dir / f"scene_{scene_num}_ready.mp4"
        trim_cmd = [_get_ffmpeg(), "-y", "-i", str(cropped), "-t", str(duration), "-c", "copy", str(ready)]
        subprocess.run(trim_cmd, capture_output=True, text=True, timeout=30)
        cropped.unlink(missing_ok=True)
        return ready if ready.exists() else None

    return None


def assemble_video(
    script: dict,
    voiceover_path: Path,
    captions_path: Path,
    assets_manifest: list[dict],
    scenes_dir: Path,
    output_path: Path,
) -> Path:
    """Assemble all components into final video."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[Assembly] === VIDEO ASSEMBLY ===")
    print(f"[Assembly] Target: {TARGET_WIDTH}x{TARGET_HEIGHT} @ {TARGET_FPS}fps")

    # Step 1: Prepare all scene clips
    scene_paths = []
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        duration = scene["duration_seconds"]

        asset = next((a for a in assets_manifest if a["scene_number"] == scene_num), None)
        if not asset:
            print(f"[Assembly] Scene {scene_num}: No asset in manifest")
            continue

        clip_path = prepare_scene_clip(asset, scenes_dir, duration, work_dir)
        if clip_path:
            scene_paths.append(clip_path)
        else:
            print(f"[Assembly] Scene {scene_num}: Failed to prepare clip")

    if not scene_paths:
        raise RuntimeError("[Assembly] No scene clips prepared")

    # Step 2: Concatenate all scenes using FFmpeg concat demuxer
    concat_list = work_dir / "concat.txt"
    with open(concat_list, "w") as f:
        for p in scene_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    concat_output = work_dir / "concat.mp4"
    print(f"[Assembly] Concatenating {len(scene_paths)} scenes...")
    concat_cmd = [
        _get_ffmpeg(), "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(concat_output),
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[Assembly] Concat failed: {result.stderr[:300]}")
        raise RuntimeError("Scene concatenation failed")

    # Step 3: Overlay voiceover audio
    print(f"[Assembly] Adding voiceover audio...")
    audio_output = work_dir / "with_audio.mp4"
    audio_cmd = [
        _get_ffmpeg(), "-y",
        "-i", str(concat_output),
        "-i", str(voiceover_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        str(audio_output),
    ]
    result = subprocess.run(audio_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[Assembly] Audio overlay failed: {result.stderr[:300]}")
        raise RuntimeError("Audio overlay failed")

    # Step 4: Burn captions
    if captions_path.exists():
        print(f"[Assembly] Burning captions...")
        srt_posix = captions_path.as_posix().replace("'", "\\'")

        fontsize = CONFIG.get("captions", {}).get("font_size", 52)
        text_color = CONFIG.get("captions", {}).get("color", "white")
        outline_color = CONFIG.get("captions", {}).get("outline_color", "black")
        outline_width = CONFIG.get("captions", {}).get("outline_width", 3)

        vf = (
            f"subtitles='{srt_posix}':"
            f"force_style='FontSize={fontsize},PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BorderStyle=3,Outline={outline_width},"
            f"Alignment=2,MarginV=80'"
        )

        caption_cmd = [
            _get_ffmpeg(), "-y",
            "-i", str(audio_output),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            str(output_path),
        ]
        result = subprocess.run(caption_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[Assembly] Caption burn failed: {result.stderr[:300]}")
            print(f"[Assembly] Using video without captions")
            import shutil
            shutil.copy2(audio_output, output_path)
    else:
        print(f"[Assembly] No captions, using audio-only video")
        import shutil
        shutil.copy2(audio_output, output_path)

    # Cleanup work directory
    for f in work_dir.iterdir():
        f.unlink(missing_ok=True)
    work_dir.rmdir()

    file_size = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[Assembly] DONE: {output_path} ({file_size:.1f} MB)")

    return output_path


if __name__ == "__main__":
    test_dir = None
    for d in [Path("output/test_gemma"), Path("output/test_script")]:
        if (d / "script.json").exists():
            test_dir = d
            break

    if not test_dir:
        print("No test script found. Run script_generator.py first.")
        raise SystemExit(1)

    script = json.loads((test_dir / "script.json").read_text())
    voiceover = test_dir / "voiceover.wav"
    captions = test_dir / "captions.srt"
    scenes_dir = test_dir / "scenes"
    assets_file = test_dir / "assets.json"

    if not voiceover.exists():
        from pipeline.voiceover import generate_voiceover
        generate_voiceover(script, test_dir)

    if not captions.exists():
        from pipeline.caption_generator import generate_captions
        generate_captions(voiceover, test_dir)

    assets = json.loads(assets_file.read_text()) if assets_file.exists() else []

    output_file = test_dir / "final.mp4"
    assemble_video(script, voiceover, captions, assets, scenes_dir, output_file)
