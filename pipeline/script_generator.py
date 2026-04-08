"""
Script Generator — Creates YouTube Shorts scripts with scene breakdowns.

Uses OpenRouter (Step 3.5 Flash) to generate:
- Hook that grabs in 2 seconds
- 4 scenes with narration + visual prompts
- Optimized for the rare/creepy history niche
"""

import json
import os
import re
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

SYSTEM_PROMPT = """You are an elite YouTube Shorts scriptwriter for a channel called HistoryShorts.
Your niche: RARE, CREEPY, and OBSCURE historical facts that most people have NEVER heard of.

Your scripts go viral because:
1. The HOOK (first 3 seconds) is impossible to scroll past
2. Every sentence builds tension or reveals something shocking
3. The ending leaves viewers stunned or wanting to share

STYLE RULES:
- Tone: mysterious, slightly dramatic, like telling a secret around a campfire
- Use short punchy sentences. No fluff. No filler.
- Start with a pattern interrupt: "In 1842, an entire town vanished overnight..." NOT "Did you know that..."
- Build tension across scenes — each reveal should be bigger than the last
- End with a chilling final line or unanswered question
- NEVER use generic openings like "Throughout history..." or "Many people don't know..."
- Total narration must fit 45-60 seconds when spoken (roughly 120-160 words total)"""

GENERATION_PROMPT = """Write a YouTube Short script about this topic:

TOPIC: {topic_title}
CONTEXT: {topic_summary}

Requirements:
- Exactly 4 scenes
- Total narration: 120-160 words (45-60 seconds spoken)
- Each scene: 10-15 seconds of narration
- Scene 1: The HOOK — pattern interrupt, make them stop scrolling
- Scene 2: Build context — set the stage, introduce the eerie detail
- Scene 3: The revelation — the darkest/most shocking part
- Scene 4: The twist/aftermath — chilling conclusion or unresolved mystery

Respond ONLY with this JSON (no markdown, no extra text):
{{
  "title": "<hook title under 60 chars, NO generic titles>",
  "hook": "<first 5-7 words that grab attention>",
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "<exact words to speak — punchy, dramatic>",
      "duration_seconds": 12,
      "visual_prompt": "<detailed image/video description for AI generation — cinematic, dark, atmospheric>",
      "pexels_search": "<2-3 word search term for stock footage>"
    }},
    {{
      "scene_number": 2,
      "narration": "<exact words>",
      "duration_seconds": 13,
      "visual_prompt": "<detailed visual description>",
      "pexels_search": "<search term>"
    }},
    {{
      "scene_number": 3,
      "narration": "<exact words>",
      "duration_seconds": 13,
      "visual_prompt": "<detailed visual description>",
      "pexels_search": "<search term>"
    }},
    {{
      "scene_number": 4,
      "narration": "<exact words>",
      "duration_seconds": 12,
      "visual_prompt": "<detailed visual description>",
      "pexels_search": "<search term>"
    }}
  ],
  "summary": "<2 sentence YouTube description — intriguing, makes people click>",
  "topic_tag": "<singletopicword for hashtag>"
}}"""


def generate_script(topic: dict, output_dir: Path, max_retries: int = 2) -> dict:
    """Generate a script from a topic. Retries on malformed JSON."""
    topic_title = topic.get("topic_title", "Unknown topic")
    topic_summary = topic.get("topic_summary", "")

    prompt = GENERATION_PROMPT.format(
        topic_title=topic_title,
        topic_summary=topic_summary,
    )

    models = [
        "stepfun/step-3.5-flash:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(max_retries + 1):
        # Try each model in fallback chain
        data = None
        for model in models:
            try:
                payload = json.dumps({
                    "model": model,
                    "messages": messages,
                    "max_tokens": 800,
                    "temperature": 0.8,
                })
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=payload.encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode())
                print(f"[ScriptGen] Using model: {model}")
                break
            except Exception as e:
                print(f"[ScriptGen] Model {model} failed: {e}")
                continue

        if not data:
            raise RuntimeError("All AI models failed")

        try:

            content = data["choices"][0]["message"]["content"].strip()

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                raise ValueError(f"No JSON in response: {content[:200]}")

            script = json.loads(json_match.group())

            # Validate structure
            if "scenes" not in script or len(script["scenes"]) < 3:
                raise ValueError(f"Invalid scene count: {len(script.get('scenes', []))}")

            for i, scene in enumerate(script["scenes"]):
                required = ["scene_number", "narration", "duration_seconds", "visual_prompt", "pexels_search"]
                for field in required:
                    if field not in scene:
                        raise ValueError(f"Scene {i} missing field: {field}")

            # Ensure required top-level fields
            for field in ["title", "hook", "summary", "topic_tag"]:
                if field not in script:
                    raise ValueError(f"Missing top-level field: {field}")

            # Save script
            output_dir.mkdir(parents=True, exist_ok=True)
            script_path = output_dir / "script.json"
            script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False))
            print(f"[ScriptGen] Script saved to {script_path}")

            # Calculate word count for duration estimate
            total_words = sum(len(s["narration"].split()) for s in script["scenes"])
            total_duration = sum(s["duration_seconds"] for s in script["scenes"])
            print(f"[ScriptGen] Total words: {total_words}, Est. duration: {total_duration}s")

            return script

        except Exception as e:
            print(f"[ScriptGen] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries:
                raise RuntimeError(f"Script generation failed after {max_retries + 1} attempts: {e}")

    raise RuntimeError("Script generation failed unexpectedly")


if __name__ == "__main__":
    # Standalone test: fetch topic then generate script
    from pipeline.topic_fetcher import fetch_topic

    print("=" * 60)
    print("STEP 1: Fetching topic...")
    print("=" * 60)
    topic = fetch_topic()

    print("\n" + "=" * 60)
    print("STEP 2: Generating script...")
    print("=" * 60)
    test_output = Path("output/test_script")
    script = generate_script(topic, test_output)

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Title: {script['title']}")
    print(f"Hook: {script['hook']}")
    for scene in script["scenes"]:
        print(f"\nScene {scene['scene_number']} ({scene['duration_seconds']}s):")
        print(f"  Narration: {scene['narration']}")
        print(f"  Visual: {scene['visual_prompt']}")
    print(f"\nSummary: {script['summary']}")
    print(f"Tag: #{script['topic_tag']}")
