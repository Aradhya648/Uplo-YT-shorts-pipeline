"""
Caption Generator — Transcribes voiceover audio to timed SRT captions.

Uses faster-whisper for word-level timestamps, outputs standard SRT format.
"""

import json
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_captions(audio_path: Path, output_dir: Path, max_words_per_segment: int = 6) -> Path:
    """Generate SRT captions from audio using faster-whisper."""
    # Import here to avoid slow load at module level
    from faster_whisper import WhisperModel

    output_dir.mkdir(parents=True, exist_ok=True)
    srt_path = output_dir / "captions.srt"

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"[Captions] Loading Whisper model (base)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")

    print(f"[Captions] Transcribing: {audio_path}")
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en",
    )

    print(f"[Captions] Detected language: {info.language} (prob: {info.language_probability:.2f})")

    # Collect all words with timestamps
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

    # Group words into caption segments (max N words per line)
    srt_entries = []
    idx = 1
    i = 0
    while i < len(all_words):
        chunk = all_words[i:i + max_words_per_segment]
        start_time = chunk[0]["start"]
        end_time = chunk[-1]["end"]
        text = " ".join(w["word"] for w in chunk)

        srt_entries.append({
            "index": idx,
            "start": start_time,
            "end": end_time,
            "text": text,
        })
        idx += 1
        i += max_words_per_segment

    # Write SRT file
    srt_lines = []
    for entry in srt_entries:
        srt_lines.append(str(entry["index"]))
        srt_lines.append(f"{format_timestamp(entry['start'])} --> {format_timestamp(entry['end'])}")
        srt_lines.append(entry["text"])
        srt_lines.append("")

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"[Captions] Saved: {srt_path} ({len(srt_entries)} segments)")

    # Also save word-level JSON for potential use in video assembly
    words_json_path = output_dir / "words.json"
    words_json_path.write_text(json.dumps(all_words, indent=2), encoding="utf-8")

    return srt_path


if __name__ == "__main__":
    # Standalone test: generate captions from test voiceover
    test_audio = Path("output/test_voiceover/voiceover.wav")
    if not test_audio.exists():
        print("No test voiceover found. Run voiceover.py first.")
        raise SystemExit(1)

    output_dir = Path("output/test_voiceover")
    srt_path = generate_captions(test_audio, output_dir)

    print(f"\nCaptions saved to: {srt_path}")
    print("\nFirst 10 lines:")
    lines = srt_path.read_text().splitlines()
    for line in lines[:10]:
        print(f"  {line}")
