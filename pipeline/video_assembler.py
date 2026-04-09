"""
Video Assembler — World-class YouTube Shorts assembly.

Features:
- Crop/resize all assets to 1080x1920
- Ken Burns zoom for static images
- Crossfade transitions between scenes
- Dark/moody color grading for creepy content
- Hook text overlay on first 3 seconds
- Punchy 3-word ALL CAPS captions (small, bottom-center)
- Voiceover audio overlay
"""

import json
import subprocess
from pathlib import Path

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


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [_get_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0


def _prepare_video_clip(input_path: Path, output_path: Path, duration: float) -> bool:
    """Crop, resize, loop if needed, apply color grading, trim to duration."""
    ffmpeg = _get_ffmpeg()
    clip_dur = _probe_duration(input_path)

    # Color grading filter: darken, increase contrast, slight desaturation for moody look
    color_grade = (
        "eq=brightness=-0.06:contrast=1.2:saturation=0.85,"
        "curves=m='0/0 0.25/0.15 0.5/0.45 0.75/0.7 1/0.9'"
    )

    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"setsar=1,"
        f"{color_grade}"
    )

    # If clip is shorter than needed, use stream_loop
    loop_args = []
    if clip_dur > 0 and clip_dur < duration - 0.5:
        loop_args = ["-stream_loop", "-1"]

    cmd = [
        ffmpeg, "-y",
        *loop_args,
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", vf,
        "-r", str(TARGET_FPS),
        "-c:v", "libx264", "-preset", "fast",
        "-an", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def _prepare_image_clip(input_path: Path, output_path: Path, duration: float) -> bool:
    """Ken Burns zoom + color grading on a static image."""
    ffmpeg = _get_ffmpeg()
    total_frames = int(duration * TARGET_FPS)

    color_grade = (
        "eq=brightness=-0.06:contrast=1.2:saturation=0.85,"
        "curves=m='0/0 0.25/0.15 0.5/0.45 0.75/0.7 1/0.9'"
    )

    vf = (
        f"zoompan=z='1+0.3*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=1080x1920:fps={TARGET_FPS},"
        f"setsar=1,"
        f"{color_grade}"
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
    return result.returncode == 0


def _add_crossfade(clips: list[Path], output_path: Path, fade_duration: float = 0.5) -> bool:
    """Concatenate clips with crossfade transitions."""
    ffmpeg = _get_ffmpeg()

    if len(clips) == 1:
        import shutil
        shutil.copy2(clips[0], output_path)
        return True

    # Build complex filter for xfade between each pair
    inputs = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    # Get durations for offset calculation
    durations = [_probe_duration(c) for c in clips]

    # Build xfade filter chain
    filter_parts = []
    current_label = "[0:v]"
    offset = durations[0] - fade_duration

    for i in range(1, len(clips)):
        next_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{current_label}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.2f}{next_label}"
        )
        current_label = next_label
        if i < len(clips) - 1:
            offset += durations[i] - fade_duration

    filter_str = ";".join(filter_parts)

    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"[Assembly] Crossfade failed, falling back to hard cuts: {result.stderr[:200]}")
        # Fallback: simple concat without crossfade
        concat_list = output_path.parent / "concat_fallback.txt"
        with open(concat_list, "w") as f:
            for c in clips:
                f.write(f"file '{c.resolve().as_posix()}'\n")
        result = subprocess.run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", str(output_path),
        ], capture_output=True, text=True, timeout=120)
        concat_list.unlink(missing_ok=True)
        return result.returncode == 0

    return True


def _add_hook_overlay(input_path: Path, output_path: Path, hook_text: str) -> bool:
    """Burn hook text on the first 3 seconds as a dramatic overlay."""
    ffmpeg = _get_ffmpeg()

    # Escape special characters for FFmpeg drawtext
    safe_text = hook_text.upper().replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")

    font_path = "C\\:/Windows/Fonts/arialbd.ttf"

    # Hook text: large, white, center screen, fades in and out
    drawtext = (
        f"drawtext=text='{safe_text}':"
        f"fontfile='{font_path}':"
        f"fontsize=56:fontcolor=white:borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:"
        f"enable='between(t\\,0.3\\,3)':"
        f"alpha='if(lt(t\\,0.8)\\,((t-0.3)/0.5)\\,if(gt(t\\,2.5)\\,(3-t)/0.5\\,1))'"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"[Assembly] Hook overlay failed: {result.stderr[:200]}")
        return False
    return True


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
    ffmpeg = _get_ffmpeg()

    print(f"\n[Assembly] === VIDEO ASSEMBLY (Quality Mode) ===")
    print(f"[Assembly] Target: {TARGET_WIDTH}x{TARGET_HEIGHT} @ {TARGET_FPS}fps")

    # Step 1: Prepare all scene clips (crop, resize, color grade)
    scene_clips = []
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        duration = scene["duration_seconds"]

        asset = next((a for a in assets_manifest if a["scene_number"] == scene_num), None)
        if not asset or not asset.get("path"):
            print(f"[Assembly] Scene {scene_num}: No asset, skipping")
            continue

        asset_path = scenes_dir / Path(asset["path"]).name
        if not asset_path.exists():
            asset_path = Path(asset["path"])
        if not asset_path.exists():
            print(f"[Assembly] Scene {scene_num}: File not found")
            continue

        is_image = asset_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']
        ready_clip = work_dir / f"scene_{scene_num}_ready.mp4"

        if is_image:
            print(f"[Assembly] Scene {scene_num}: Ken Burns + color grade ({duration}s)")
            ok = _prepare_image_clip(asset_path, ready_clip, duration)
        else:
            src_dur = _probe_duration(asset_path)
            print(f"[Assembly] Scene {scene_num}: Video {src_dur:.1f}s -> {duration}s + color grade")
            ok = _prepare_video_clip(asset_path, ready_clip, duration)

        if ok and ready_clip.exists():
            scene_clips.append(ready_clip)
        else:
            print(f"[Assembly] Scene {scene_num}: Preparation failed")

    if not scene_clips:
        raise RuntimeError("[Assembly] No scene clips prepared")

    # Step 2: Concatenate with crossfade transitions
    print(f"[Assembly] Adding crossfade transitions between {len(scene_clips)} scenes...")
    crossfaded = work_dir / "crossfaded.mp4"
    _add_crossfade(scene_clips, crossfaded)

    # Step 3: Add voiceover audio
    print(f"[Assembly] Overlaying voiceover audio...")
    with_audio = work_dir / "with_audio.mp4"
    result = subprocess.run([
        ffmpeg, "-y",
        "-i", str(crossfaded),
        "-i", str(voiceover_path),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        str(with_audio),
    ], capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise RuntimeError(f"Audio overlay failed: {result.stderr[:200]}")

    # Step 4: Burn captions — small, bottom, ALL CAPS
    print(f"[Assembly] Burning captions...")
    with_captions = work_dir / "with_captions.mp4"
    if captions_path.exists():
        srt_posix = captions_path.as_posix().replace("'", "\\'")
        # Small font, white text with black outline, bottom center
        # MarginV=120 pushes it above the very bottom (avoids YouTube UI overlap)
        vf = (
            f"subtitles='{srt_posix}':"
            f"force_style='FontSize=24,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BorderStyle=3,Outline=2,"
            f"Bold=1,Alignment=2,MarginV=120'"
        )
        result = subprocess.run([
            ffmpeg, "-y",
            "-i", str(with_audio),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            str(with_captions),
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            print(f"[Assembly] Caption burn failed, using video without captions")
            with_captions = with_audio
    else:
        with_captions = with_audio

    # Step 5: Add hook text overlay on first 3 seconds
    hook_text = script.get("hook", "")
    if hook_text:
        print(f"[Assembly] Adding hook overlay: '{hook_text}'")
        with_hook = work_dir / "with_hook.mp4"
        if _add_hook_overlay(with_captions, with_hook, hook_text):
            final_source = with_hook
        else:
            final_source = with_captions
    else:
        final_source = with_captions

    # Step 6: Copy to final output
    import shutil
    shutil.copy2(final_source, output_path)

    # Cleanup work directory
    for f in work_dir.iterdir():
        f.unlink(missing_ok=True)
    work_dir.rmdir()

    file_size = output_path.stat().st_size / (1024 * 1024)
    dur = _probe_duration(output_path)
    print(f"\n[Assembly] DONE: {output_path} ({file_size:.1f} MB, {dur:.1f}s)")

    return output_path


if __name__ == "__main__":
    test_dir = None
    for d in [Path("output/test_quality"), Path("output/test_gemma")]:
        if (d / "script.json").exists():
            test_dir = d
            break

    if not test_dir:
        print("No test script found.")
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
