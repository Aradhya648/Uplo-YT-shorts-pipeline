"""
Voiceover Generator — Converts script narrations to audio using Piper TTS.

Concatenates all scene narrations into a single text, generates WAV via Piper,
and saves to output/{run_id}/voiceover.wav.
"""

import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PIPER_MODEL_PATH = Path(os.getenv("PIPER_MODEL_PATH", "assets/piper-models/en_US-lessac-medium.onnx"))
PIPER_SPEED = float(os.getenv("PIPER_SPEED", "1.0"))


def generate_voiceover(script: dict, output_dir: Path) -> Path:
    """Generate voiceover WAV from script narrations using Piper TTS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "voiceover.wav"

    # Concatenate all scene narrations with pauses between scenes
    narrations = []
    for scene in script["scenes"]:
        narrations.append(scene["narration"])

    full_text = " ... ".join(narrations)
    print(f"[Voiceover] Text length: {len(full_text.split())} words")
    print(f"[Voiceover] Model: {PIPER_MODEL_PATH}")

    # Resolve model path relative to project root
    model_path = PIPER_MODEL_PATH
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path

    if not model_path.exists():
        raise FileNotFoundError(f"Piper model not found: {model_path}")

    # Build Piper command
    cmd = [
        "python", "-m", "piper",
        "--model", str(model_path),
        "--output_file", str(output_path),
        "--length-scale", str(1.0 / PIPER_SPEED),
        "--sentence-silence", "0.4",
    ]

    # Pipe text to Piper via stdin
    print(f"[Voiceover] Generating audio...")
    result = subprocess.run(
        cmd,
        input=full_text,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Piper TTS failed: {result.stderr}")

    if not output_path.exists():
        raise FileNotFoundError(f"Voiceover not generated: {output_path}")

    file_size = output_path.stat().st_size
    print(f"[Voiceover] Saved: {output_path} ({file_size / 1024:.1f} KB)")

    return output_path


if __name__ == "__main__":
    # Standalone test: load script.json from test output and generate voiceover
    test_script_path = Path("output/test_script/script.json")
    if not test_script_path.exists():
        print("No test script found. Run script_generator.py first.")
        print("Generating with sample script...")
        script = {
            "scenes": [
                {"scene_number": 1, "narration": "In 1518, a woman stepped into the streets of Strasbourg and began to dance. She couldn't stop.", "duration_seconds": 12},
                {"scene_number": 2, "narration": "Within a week, thirty-four others had joined her. Their feet bled. Their bodies collapsed. But still, they danced.", "duration_seconds": 13},
                {"scene_number": 3, "narration": "The city's physicians were baffled. They prescribed more dancing, building a stage and hiring musicians. It only made things worse.", "duration_seconds": 13},
                {"scene_number": 4, "narration": "By September, hundreds had been afflicted. Some danced themselves to death. To this day, no one knows why.", "duration_seconds": 12},
            ]
        }
    else:
        script = json.loads(test_script_path.read_text())

    output_dir = Path("output/test_voiceover")
    wav_path = generate_voiceover(script, output_dir)
    print(f"\nVoiceover saved to: {wav_path}")
