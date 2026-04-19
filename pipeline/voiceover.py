"""
Voiceover Generator — ElevenLabs Rachel (paid) with Edge TTS fallback (free).

Primary:  ElevenLabs Rachel — eleven_multilingual_v2, stability 0.4, similarity 0.8
Fallback: Edge TTS en-US-GuyNeural (kicks in automatically on free-tier 402 errors)
"""

import asyncio
import glob as _glob
import json
import os
import shutil
import subprocess
from pathlib import Path

import edge_tts
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
MODEL_ID = "eleven_multilingual_v2"
VOICE_NAME = "Rachel"
RACHEL_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # known stable ID

# Edge TTS fallback config (used when ElevenLabs is on free tier)
EDGE_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
EDGE_RATE  = os.getenv("TTS_RATE", "-5%")
EDGE_PITCH = os.getenv("TTS_PITCH", "-2Hz")


def _find_ffmpeg() -> str:
    """Locate ffmpeg: PATH → current-user WinGet → Aradhya WinGet → bare 'ffmpeg'."""
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


_FFMPEG_EXE = _find_ffmpeg()


def _get_ffmpeg() -> str:
    return _FFMPEG_EXE


# ---------------------------------------------------------------------------
# ElevenLabs path
# ---------------------------------------------------------------------------

def _try_elevenlabs(scenes: list[dict], work_dir: Path) -> list[Path] | None:
    """
    Attempt to generate all scene audio via ElevenLabs.
    Returns list of Paths on success, None if unavailable (no key or 402).
    """
    if not ELEVENLABS_API_KEY:
        print("[Voiceover] ELEVENLABS_API_KEY not set — using Edge TTS fallback")
        return None

    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings
    except ImportError:
        print("[Voiceover] elevenlabs package not installed — using Edge TTS fallback")
        return None

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    # Resolve voice ID
    voice_id = RACHEL_VOICE_ID
    try:
        voices = client.voices.get_all()
        for v in voices.voices:
            if v.name.lower() == VOICE_NAME.lower():
                voice_id = v.voice_id
                break
    except Exception:
        pass  # use fallback ID

    scene_files = []
    for scene in scenes:
        scene_num = scene["scene_number"]
        narration = scene["narration"]
        out = work_dir / f"scene_{scene_num}.mp3"
        print(f"[Voiceover] ElevenLabs scene {scene_num}: {len(narration.split())} words")
        try:
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                text=narration,
                model_id=MODEL_ID,
                voice_settings=VoiceSettings(
                    stability=0.4,
                    similarity_boost=0.8,
                    style=0.6,
                    use_speaker_boost=True,
                ),
                output_format="mp3_44100_128",
            )
            with open(out, "wb") as f:
                for chunk in audio_stream:
                    if chunk:
                        f.write(chunk)
            scene_files.append(out)
        except Exception as e:
            msg = str(e)
            if "402" in msg or "payment_required" in msg or "paid_plan_required" in msg:
                print(
                    "[Voiceover] ElevenLabs requires a paid plan for this voice. "
                    "Switching to Edge TTS fallback."
                )
                return None
            raise  # unexpected error — propagate

    return scene_files


# ---------------------------------------------------------------------------
# Edge TTS fallback path
# ---------------------------------------------------------------------------

async def _edge_scene(text: str, out: Path) -> Path:
    comm = edge_tts.Communicate(text, voice=EDGE_VOICE, rate=EDGE_RATE, pitch=EDGE_PITCH)
    await comm.save(str(out))
    return out


async def _edge_all_scenes(scenes: list[dict], work_dir: Path) -> list[Path]:
    files = []
    for scene in scenes:
        out = work_dir / f"scene_{scene['scene_number']}.mp3"
        print(f"[Voiceover] EdgeTTS scene {scene['scene_number']}: {len(scene['narration'].split())} words")
        await _edge_scene(scene["narration"], out)
        files.append(out)
    return files


# ---------------------------------------------------------------------------
# Shared FFmpeg assembly
# ---------------------------------------------------------------------------

def _assemble_wav(scene_files: list[Path], work_dir: Path, output_path: Path) -> None:
    """Add silence between scenes, concatenate, convert to 16 kHz mono WAV."""
    ffmpeg = _get_ffmpeg()

    silence_path = work_dir / "silence.mp3"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i",
        "anullsrc=r=24000:cl=mono", "-t", "0.5",
        "-c:a", "libmp3lame", str(silence_path),
    ], capture_output=True, timeout=10)

    concat_list = work_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for i, sf in enumerate(scene_files):
            f.write(f"file '{sf.resolve().as_posix()}'\n")
            if i < len(scene_files) - 1:
                f.write(f"file '{silence_path.resolve().as_posix()}'\n")

    concat_output = work_dir / "combined.mp3"
    result = subprocess.run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(concat_output),
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:300]}")

    result = subprocess.run([
        ffmpeg, "-y", "-i", str(concat_output),
        "-ar", "16000", "-ac", "1", str(output_path),
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg WAV conversion failed: {result.stderr[:300]}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_voiceover(script: dict, output_dir: Path) -> Path:
    """Generate voiceover WAV. Uses ElevenLabs Rachel if paid plan, else Edge TTS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "vo_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "voiceover.wav"

    scenes = script["scenes"]
    total_words = sum(len(s["narration"].split()) for s in scenes)

    # Try ElevenLabs first
    print(f"[Voiceover] Attempting ElevenLabs Rachel ({total_words} words, {len(scenes)} scenes)")
    scene_files = _try_elevenlabs(scenes, work_dir)

    # Fall back to Edge TTS if needed
    if scene_files is None:
        print(f"[Voiceover] Edge TTS fallback | Voice: {EDGE_VOICE} | {total_words} words")
        scene_files = asyncio.run(_edge_all_scenes(scenes, work_dir))

    print(f"[Voiceover] Assembling {len(scene_files)} scenes into WAV...")
    _assemble_wav(scene_files, work_dir, output_path)

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
    output_dir = Path("output/test_elevenlabs")
    wav_path = generate_voiceover(script, output_dir)
    print(f"\nVoiceover saved to: {wav_path}")
