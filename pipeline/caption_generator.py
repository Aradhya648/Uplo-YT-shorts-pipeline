"""
Caption Generator — Transcribes voiceover to timed ASS captions.

Uses faster-whisper for word-level timestamps.
Outputs short 2-3 word segments for punchy YouTube Shorts style captions.
"""

import json
import os
from pathlib import Path

import yaml

# Must be set before ctranslate2 is imported anywhere — prevents mkl_malloc crash
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

_config_path = Path(__file__).parent.parent / "config.yaml"
if _config_path.exists():
    with open(_config_path) as f:
        _CONFIG = yaml.safe_load(f)
else:
    _CONFIG = {}


def _format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cs (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _maybe_wrap(text: str) -> str:
    """Insert \\N hard line break at the middle word if text exceeds 18 chars."""
    if len(text) <= 18:
        return text
    words = text.split()
    if len(words) <= 1:
        return text
    mid = (len(words) + 1) // 2
    return " ".join(words[:mid]) + r"\N" + " ".join(words[mid:])


def generate_captions(audio_path: Path, output_dir: Path, max_words_per_segment: int = 3) -> Path:
    """Generate ASS captions from audio using faster-whisper.

    Uses 3-word segments for punchy, YouTube Shorts-style captions.
    Font size is read from config.yaml (captions.font_size).
    """
    from faster_whisper import WhisperModel

    font_size = _CONFIG.get("captions", {}).get("font_size", 52)

    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / "captions.ass"

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"[Captions] Loading Whisper model (base)...")
    model = WhisperModel("base", device="cpu", compute_type="float32", cpu_threads=1)

    print(f"[Captions] Transcribing: {audio_path}")
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en",
    )

    print(f"[Captions] Detected language: {info.language} (prob: {info.language_probability:.2f})")

    all_words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                all_words.append({
                    "word": word.word.strip(),
                    "start": word.start,
                    "end": word.end,
                })

    if not all_words:
        raise ValueError("No words transcribed from audio")

    print(f"[Captions] Transcribed {len(all_words)} words")

    entries = []
    i = 0
    while i < len(all_words):
        chunk = all_words[i:i + max_words_per_segment]
        raw_text = " ".join(w["word"] for w in chunk).upper()
        entries.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": _maybe_wrap(raw_text),
        })
        i += max_words_per_segment

    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Impact,{font_size},&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,1,2,20,20,350,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for entry in entries:
        t0 = _format_ass_time(entry["start"])
        t1 = _format_ass_time(entry["end"])
        ass_lines.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{entry['text']}")

    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")
    print(f"[Captions] Saved: {ass_path} ({len(entries)} segments, {max_words_per_segment} words/seg, fontsize={font_size})")

    words_json_path = output_dir / "words.json"
    words_json_path.write_text(json.dumps(all_words, indent=2), encoding="utf-8")

    return ass_path


if __name__ == "__main__":
    test_audio = Path("output/test_quality/voiceover.wav")
    if not test_audio.exists():
        print("No test voiceover found. Run voiceover.py first.")
        raise SystemExit(1)

    output_dir = Path("output/test_quality")
    ass_path = generate_captions(test_audio, output_dir)

    print(f"\nCaptions saved to: {ass_path}")
    print("\nFirst 20 lines:")
    lines = ass_path.read_text().splitlines()
    for line in lines[:20]:
        print(f"  {line}")
