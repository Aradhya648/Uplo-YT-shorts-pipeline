"""
Video Assembler — Viral YouTube Shorts style assembly.

Features:
- Crop/resize all assets to 1080x1920
- Ken Burns zoom for static images
- Crossfade transitions between scenes
- Warm cinematic color grading
- Large centered bold captions (Impact font, 76px, center-screen)
- FACT #1 / FACT #2 / FACT #3 section labels at each scene
- Title card overlay on first 2.5 seconds
- "FOLLOW FOR MORE" CTA in last 2.5 seconds
- Background music mixing (drop bgm.mp3 in assets/bgm/ to enable)
- Voiceover audio overlay
"""

import glob as _glob
import json
import os
import re
import shutil
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

BGM_PATH = Path(__file__).parent.parent / "assets" / "bgm" / "bgm.mp3"

# Warm cinematic color grade — vivid, natural brightness, warm tones
_COLOR_GRADE = (
    "eq=brightness=-0.02:contrast=1.15:saturation=1.1,"
    "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.44 1/0.93'"
)


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        pattern = str(
            Path(local_appdata) / "Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"
        )
        matches = sorted(_glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    aradhya = Path(
        "C:/Users/91979/AppData/Local/Microsoft/WinGet/Packages"
        "/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        "/ffmpeg-8.1-full_build/bin/ffmpeg.exe"
    )
    if aradhya.exists():
        return str(aradhya)
    return "ffmpeg"


def _find_ffprobe() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        pattern = str(
            Path(local_appdata) / "Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffprobe.exe"
        )
        matches = sorted(_glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    aradhya = Path(
        "C:/Users/91979/AppData/Local/Microsoft/WinGet/Packages"
        "/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        "/ffmpeg-8.1-full_build/bin/ffprobe.exe"
    )
    if aradhya.exists():
        return str(aradhya)
    return "ffprobe"


_FFMPEG_EXE = _find_ffmpeg()
_FFPROBE_EXE = _find_ffprobe()


def _get_ffmpeg() -> str:
    return _FFMPEG_EXE


def _get_ffprobe() -> str:
    return _FFPROBE_EXE


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [_get_ffmpeg(), "-i", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        return 0
    except Exception:
        return 0


def _prepare_video_clip(input_path: Path, output_path: Path, duration: float) -> bool:
    """Crop, resize, loop if needed, apply warm color grade, trim to duration."""
    ffmpeg = _get_ffmpeg()
    clip_dur = _probe_duration(input_path)

    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"setsar=1,"
        f"{_COLOR_GRADE}"
    )

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
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        "-an", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def _prepare_image_clip(input_path: Path, output_path: Path, duration: float) -> bool:
    """Ken Burns zoom + warm color grade on a static image."""
    ffmpeg = _get_ffmpeg()
    total_frames = int(duration * TARGET_FPS)

    vf = (
        f"zoompan=z='1+0.3*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=1080x1920:fps={TARGET_FPS},"
        f"setsar=1,"
        f"{_COLOR_GRADE}"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


def _add_crossfade(clips: list[Path], output_path: Path, fade_duration: float = 0.5) -> bool:
    """Concatenate clips with crossfade transitions."""
    ffmpeg = _get_ffmpeg()

    if len(clips) == 1:
        shutil.copy2(clips[0], output_path)
        return True

    inputs = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    durations = [_probe_duration(c) for c in clips]

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
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"[Assembly] Crossfade failed, falling back to hard cuts: {result.stderr[:200]}")
        concat_list = output_path.parent / "concat_fallback.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c.resolve().as_posix()}'\n")
        result = subprocess.run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:v", "libx264", "-preset", "fast", "-threads", "1",
            "-pix_fmt", "yuv420p", str(output_path),
        ], capture_output=True, text=True, timeout=120)
        concat_list.unlink(missing_ok=True)
        return result.returncode == 0

    return True


def _find_font() -> str:
    """Find Impact (or bold fallback) for FFmpeg drawtext with Windows escaping."""
    candidates = [
        Path("C:/Windows/Fonts/impact.ttf"),                               # Impact — viral Shorts default
        Path("C:/Windows/Fonts/arialbd.ttf"),                              # Arial Bold
        Path("/System/Library/Fonts/Supplemental/Impact.ttf"),              # macOS
        Path("/usr/share/fonts/truetype/msttcorefonts/Impact.ttf"),         # Linux
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),          # macOS
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),       # Linux
    ]
    for p in candidates:
        if p.exists():
            s = p.as_posix()
            # FFmpeg drawtext requires escaping the colon in Windows drive letters
            if len(s) >= 2 and s[1] == ":":
                s = s[0] + "\\:" + s[2:]
            return s
    return ""


def _esc(text: str) -> str:
    """Escape text for FFmpeg drawtext filter value."""
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")


def _add_captions(input_path: Path, output_path: Path, captions_path: Path) -> bool:
    """Burn ASS captions — all style/position/font defined in the .ass file."""
    ffmpeg = _get_ffmpeg()
    ass_posix = captions_path.as_posix().replace("'", "\\'")
    vf = f"ass='{ass_posix}'"
    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        "-c:a", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"[Assembly] Caption burn failed: {result.stderr[:200]}")
        return False
    return True


def _add_all_overlays(
    input_path: Path,
    output_path: Path,
    script: dict,
    scene_start_times: list[float],
) -> bool:
    """Add title card, FACT #N section labels, and FOLLOW FOR MORE CTA."""
    ffmpeg = _get_ffmpeg()
    total_dur = _probe_duration(input_path)
    font_path = _find_font()
    ff = f"fontfile='{font_path}':" if font_path else ""
    dt = []  # list of drawtext filter strings

    # ── Title card (first 2.5 seconds) — clean pill box, no raw text ────────
    raw_title = script.get("title", "").upper()
    words = raw_title.split()
    if len(words) >= 4:
        mid = (len(words) + 1) // 2
        line1 = _esc(" ".join(words[:mid]))
        line2 = _esc(" ".join(words[mid:]))
    else:
        line1 = _esc(raw_title)
        line2 = ""

    if line1:
        y1 = "(h/2)-420" if line2 else "(h/2)-160"
        dt.append(
            f"drawtext=text='{line1}':{ff}"
            f"fontsize=52:fontcolor=white:borderw=3:bordercolor=black:"
            f"box=1:boxcolor=black@0.65:boxborderw=24:"
            f"x=(w-text_w)/2:y={y1}:enable='between(t\\,0.1\\,2.5)'"
        )
    if line2:
        dt.append(
            f"drawtext=text='{line2}':{ff}"
            f"fontsize=52:fontcolor=white:borderw=3:bordercolor=black:"
            f"box=1:boxcolor=black@0.65:boxborderw=24:"
            f"x=(w-text_w)/2:y=(h/2)-340:enable='between(t\\,0.1\\,2.5)'"
        )

    # ── FOLLOW FOR MORE CTA (last 2.5 seconds) ───────────────────────────────
    cta_t0 = max(0.0, total_dur - 2.5)
    dt.append(
        f"drawtext=text='FOLLOW FOR MORE':{ff}"
        f"fontsize=46:fontcolor=white:borderw=3:bordercolor=black:"
        f"box=1:boxcolor=black@0.60:boxborderw=20:"
        f"x=(w-text_w)/2:y=h-280:enable='between(t\\,{cta_t0:.2f}\\,{total_dur:.2f})'"
    )

    vf = ",".join(dt)
    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-threads", "1",
        "-c:a", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"[Assembly] Overlay pass failed, skipping: {result.stderr[:300]}")
        shutil.copy2(input_path, output_path)
        return False
    return True


def _mix_bgm(input_path: Path, bgm_path: Path, output_path: Path) -> bool:
    """Mix background music at 15% volume with 1s fade-in/out under the voiceover."""
    ffmpeg = _get_ffmpeg()
    vo_dur = _probe_duration(input_path)
    fade_out_start = max(0.0, vo_dur - 1.5)
    filter_complex = (
        f"[1:a]volume=0.15,afade=t=in:st=0:d=1,afade=t=out:st={fade_out_start:.2f}:d=1.5[bgm];"
        "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"[Assembly] BGM mix failed: {result.stderr[:200]}")
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
    """Assemble all components into final viral-style Shorts video."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _get_ffmpeg()

    print(f"\n[Assembly] === VIDEO ASSEMBLY (Viral Shorts Style) ===")
    print(f"[Assembly] Target: {TARGET_WIDTH}x{TARGET_HEIGHT} @ {TARGET_FPS}fps")

    # Step 1: Prepare all scene clips
    scene_clips: list[Path] = []
    scene_clip_script_indices: list[int] = []

    for idx, scene in enumerate(script["scenes"]):
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

        is_image = asset_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
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
            scene_clip_script_indices.append(idx)
        else:
            print(f"[Assembly] Scene {scene_num}: Preparation failed")

    if not scene_clips:
        raise RuntimeError("[Assembly] No scene clips prepared")

    # Compute per-scene start times in the assembled timeline (crossfade eats 0.5s per cut)
    FADE_DUR = 0.5
    clip_durations = [_probe_duration(c) for c in scene_clips]
    clip_starts: list[float] = []
    t = 0.0
    for i, d in enumerate(clip_durations):
        clip_starts.append(t)
        t += d - (FADE_DUR if i < len(clip_durations) - 1 else 0.0)

    # Map clip-level start times back to script scene indices
    full_scene_starts = [0.0] * len(script["scenes"])
    for clip_i, scene_i in enumerate(scene_clip_script_indices):
        full_scene_starts[scene_i] = clip_starts[clip_i]

    # Step 2: Crossfade
    print(f"[Assembly] Crossfading {len(scene_clips)} scenes...")
    crossfaded = work_dir / "crossfaded.mp4"
    _add_crossfade(scene_clips, crossfaded)

    # Step 3: Voiceover
    print(f"[Assembly] Overlaying voiceover...")
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

    # Step 4: Background music (optional)
    if BGM_PATH.exists():
        print(f"[Assembly] Mixing BGM: {BGM_PATH.name}")
        with_bgm = work_dir / "with_bgm.mp4"
        if _mix_bgm(with_audio, BGM_PATH, with_bgm):
            audio_source = with_bgm
        else:
            print("[Assembly] BGM mix failed — continuing without BGM")
            audio_source = with_audio
    else:
        print(f"[Assembly] No BGM at {BGM_PATH} — drop bgm.mp3 there to enable background music")
        audio_source = with_audio

    # Step 5: Captions — large, centered, bold (viral Shorts style)
    print(f"[Assembly] Burning captions (Impact 76px, center screen)...")
    with_captions = work_dir / "with_captions.mp4"
    if captions_path.exists():
        if _add_captions(audio_source, with_captions, captions_path):
            caption_source = with_captions
        else:
            print("[Assembly] Caption burn failed — continuing without captions")
            caption_source = audio_source
    else:
        caption_source = audio_source

    # Step 6: Title card + FACT overlays + FOLLOW CTA
    print(f"[Assembly] Adding title card, FACT labels, and FOLLOW CTA...")
    with_overlays = work_dir / "with_overlays.mp4"
    _add_all_overlays(caption_source, with_overlays, script, full_scene_starts)
    final_source = with_overlays if with_overlays.exists() and with_overlays.stat().st_size > 0 else caption_source

    # Step 7: Copy to final output
    shutil.copy2(final_source, output_path)

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
    captions = test_dir / "captions.ass"
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
