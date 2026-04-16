"""
Voiceover Generator — Converts script narrations to audio using Edge TTS.

Microsoft Edge TTS provides near-human neural voices for free.
Uses en-US-GuyNeural with slightly slower rate for dramatic effect.
"""

import asyncio
import glob as _glob
import json
import os
import re
import subprocess
from pathlib import Path

import edge_tts
from dotenv import load_dotenv

load_dotenv()

# Voice config — GuyNeural is deep, dramatic, perfect for dark history
VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
RATE = os.getenv("TTS_RATE", "-5%")   # slightly slower = more dramatic
PITCH = os.getenv("TTS_PITCH", "-2Hz")  # slightly deeper

def _find_ffmpeg() -> str:
    """Locate ffmpeg.exe: CapCut bundle (latest version) then PATH."""
    capcut = sorted(
        _glob.glob(str(Path.home() / "AppData/Local/CapCut/Apps/*/ffmpeg.exe")),
        reverse=True,
    )
    if capcut:
        return capcut[0]
    return "ffmpeg"


_FFMPEG_EXE = _find_ffmpeg()


def _get_ffmpeg() -> str:
    return _FFMPEG_EXE


async def _generate_scene_audio(text: str, output_path: Path) -> Path:
    """Generate audio for a single scene narration."""
    communicate = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(str(output_path))
    return output_path


async def _generate_all_scenes(scenes: list[dict], work_dir: Path) -> list[Path]:
    """Generate audio for all scenes with pauses between them."""
    scene_files = []
    for scene in scenes:
        scene_num = scene["scene_number"]
        narration = scene["narration"]
        out = work_dir / f"scene_{scene_num}.mp3"
        print(f"[Voiceover] Scene {scene_num}: {len(narration.split())} words")
        await _generate_scene_audio(narration, out)
        scene_files.append(out)
    return scene_files


def generate_voiceover(script: dict, output_dir: Path) -> Path:
    """Generate voiceover WAV from script narrations using Edge TTS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "vo_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "voiceover.wav"

    scenes = script["scenes"]
    total_words = sum(len(s["narration"].split()) for s in scenes)
    print(f"[Voiceover] Voice: {VOICE}, Rate: {RATE}, Pitch: {PITCH}")
    print(f"[Voiceover] Total: {total_words} words across {len(scenes)} scenes")

    # Generate per-scene audio
    scene_files = asyncio.run(_generate_all_scenes(scenes, work_dir))

    # Generate a 0.5s silence file for pauses between scenes
    silence_path = work_dir / "silence.mp3"
    ffmpeg = _get_ffmpeg()
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "anullsrc=r=24000:cl=mono", "-t", "0.5",
        "-c:a", "libmp3lame", str(silence_path),
    ], capture_output=True, timeout=10)

    # Build concat list: scene1 + silence + scene2 + silence + ...
    concat_list = work_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for i, sf in enumerate(scene_files):
            f.write(f"file '{sf.resolve().as_posix()}'\n")
            if i < len(scene_files) - 1:
                f.write(f"file '{silence_path.resolve().as_posix()}'\n")

    # Concatenate all scenes with pauses into final WAV
    print(f"[Voiceover] Concatenating {len(scene_files)} scenes with pauses...")
    concat_output = work_dir / "combined.mp3"
    result = subprocess.run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy", str(concat_output),
    ], capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:200]}")

    # Convert to WAV for compatibility with faster-whisper
    subprocess.run([
        ffmpeg, "-y", "-i", str(concat_output),
        "-ar", "16000", "-ac", "1",
        str(output_path),
    ], capture_output=True, text=True, timeout=60)

    # Cleanup work dir
    for f in work_dir.iterdir():
        f.unlink(missing_ok=True)
    work_dir.rmdir()

    file_size = output_path.stat().st_size
    print(f"[Voiceover] Saved: {output_path} ({file_size / 1024:.1f} KB)")

    return output_path


if __name__ == "__main__":
    test_script_path = Path("output/test_gemma/script.json")
    if not test_script_path.exists():
        print("No test script found.")
        raise SystemExit(1)

    script = json.loads(test_script_path.read_text())
    output_dir = Path("output/test_quality")
    wav_path = generate_voiceover(script, output_dir)
    print(f"\nVoiceover saved to: {wav_path}")
