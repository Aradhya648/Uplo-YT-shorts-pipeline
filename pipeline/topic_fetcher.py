"""
Topic Fetcher — Triple-layer research for rare/creepy historical facts.

Layers:
1. Tavily → Reddit (search Reddit via Tavily for obscure/creepy history)
2. Wikipedia "On This Day" + random obscure articles
3. Tavily → general web (depth search for forgotten history)

Then AI scoring picks the best candidate.
"""

import json
import os
import random
import re
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY")

GEMINI_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-2.5-flash-lite",
]


def _call_gemini_raw(prompt: str) -> str | None:
    """Call Gemini API. Returns raw text or None."""
    if not GOOGLE_AI_API_KEY:
        return None
    for model in GEMINI_MODELS:
        try:
            payload = json.dumps({
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7},
            })
            url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_AI_API_KEY}"
            req = urllib.request.Request(url, data=payload.encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"[TopicFetcher] AI scoring succeeded with Gemini: {model}")
            return text
        except Exception as e:
            print(f"[TopicFetcher] Gemini {model} failed: {e}")
            continue
    return None

# Niche-specific search queries for Reddit via Tavily
REDDIT_QUERIES = [
    'site:reddit.com "creepy historical fact" OR "disturbing history"',
    'site:reddit.com r/history obscure forgotten lesser-known',
    'site:reddit.com r/todayilearned history creepy eerie dark',
    'site:reddit.com r/AskHistorians bizarre unusual forgotten',
    'site:reddit.com "most disturbing thing in history" OR "darkest historical event"',
    'site:reddit.com r/creepy history true story real event',
]

# General web queries for rare history
WEB_QUERIES = [
    "obscure creepy historical facts most people don't know",
    "forgotten dark events in history",
    "eerie unsolved historical mysteries",
    "disturbing historical practices forgotten by time",
    "lesser known horrifying moments in history",
    "strangest true stories from history",
]


def fetch_reddit_via_tavily(client: TavilyClient, num_queries: int = 2) -> list[dict]:
    """Layer 1: Search Reddit content via Tavily."""
    candidates = []
    queries = random.sample(REDDIT_QUERIES, min(num_queries, len(REDDIT_QUERIES)))

    for query in queries:
        try:
            response = client.search(query=query, max_results=5, search_depth="basic")
            for result in response.get("results", []):
                candidates.append({
                    "source": "reddit_via_tavily",
                    "title": result.get("title", ""),
                    "content": result.get("content", "")[:500],
                    "url": result.get("url", ""),
                })
        except Exception as e:
            print(f"[TopicFetcher] Reddit/Tavily search failed: {e}")

    return candidates


def fetch_wikipedia_on_this_day() -> list[dict]:
    """Layer 2a: Wikipedia 'On This Day' events for today's date."""
    candidates = []
    today = datetime.now()
    month = today.strftime("%m")
    day = today.strftime("%d")

    url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{month}/{day}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HistoryShorts/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        events = data.get("events", [])
        # Shuffle and pick up to 10 events to look for unusual ones
        random.shuffle(events)
        for event in events[:10]:
            text = event.get("text", "")
            year = event.get("year", "")
            candidates.append({
                "source": "wikipedia_on_this_day",
                "title": f"On this day in {year}: {text[:80]}",
                "content": text,
                "url": "",
            })
    except Exception as e:
        print(f"[TopicFetcher] Wikipedia On This Day failed: {e}")

    return candidates


def fetch_wikipedia_random_obscure() -> list[dict]:
    """Layer 2b: Wikipedia random articles from history-related categories."""
    candidates = []
    search_terms = [
        "historical mysteries", "forgotten civilizations", "unusual deaths",
        "historical disasters", "medieval torture", "lost cities",
        "plague history", "cursed objects history", "ghost ships",
        "human experimentation history", "ancient rituals dark",
        "abandoned places history", "mass hysteria historical",
    ]
    term = random.choice(search_terms)

    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(term)}&srlimit=10&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HistoryShorts/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("query", {}).get("search", [])
        for r in results:
            # Strip HTML tags from snippet
            snippet = re.sub(r"<[^>]+>", "", r.get("snippet", ""))
            candidates.append({
                "source": "wikipedia_search",
                "title": r.get("title", ""),
                "content": snippet,
                "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(r.get('title', '').replace(' ', '_'))}",
            })
    except Exception as e:
        print(f"[TopicFetcher] Wikipedia search failed: {e}")

    return candidates


def fetch_web_via_tavily(client: TavilyClient) -> list[dict]:
    """Layer 3: General web search for obscure history via Tavily."""
    candidates = []
    query = random.choice(WEB_QUERIES)

    try:
        response = client.search(query=query, max_results=5, search_depth="advanced")
        for result in response.get("results", []):
            candidates.append({
                "source": "web_via_tavily",
                "title": result.get("title", ""),
                "content": result.get("content", "")[:500],
                "url": result.get("url", ""),
            })
    except Exception as e:
        print(f"[TopicFetcher] Web/Tavily search failed: {e}")

    return candidates


CREEPY_KEYWORDS = [
    "murder", "death", "dead", "killed", "execution", "torture", "buried", "corpse",
    "ghost", "haunted", "curse", "cursed", "ritual", "cult", "disease", "plague",
    "disappeared", "vanished", "mystery", "unsolved", "strange", "bizarre", "eerie",
    "dark", "secret", "forbidden", "hidden", "forgotten", "lost", "discovered",
    "experiment", "asylum", "witch", "demon", "possessed", "sacrifice",
]
GENERIC_KEYWORDS = [
    "world war", "hitler", "napoleon", "columbus", "washington", "lincoln",
    "revolution", "invention", "famous", "popular", "well-known", "celebrated",
]


def _keyword_score_and_pick(candidates: list[dict]) -> dict:
    """Fallback: score candidates by keyword matching when AI is unavailable."""
    def score(c: dict) -> float:
        text = (c.get("title", "") + " " + c.get("content", "")).lower()
        creep = sum(1 for kw in CREEPY_KEYWORDS if kw in text)
        generic = sum(1 for kw in GENERIC_KEYWORDS if kw in text)
        return creep - (generic * 2)

    best = max(candidates, key=score)
    return {
        "topic_title": best["title"],
        "topic_summary": best["content"],
        "scores": {},
        "source": best["source"],
        "source_url": best.get("url", ""),
        "rejection_reason": "AI unavailable, keyword-scored",
    }


def score_and_pick_best(candidates: list[dict]) -> dict:
    """Use OpenRouter AI to score candidates and pick the best one for a YouTube Short."""
    if not candidates:
        raise ValueError("No candidates found from any research layer")

    # Prepare candidate summaries for scoring
    candidate_text = ""
    for i, c in enumerate(candidates):
        candidate_text += f"\n[{i}] ({c['source']}) {c['title']}\n    {c['content'][:200]}\n"

    prompt = f"""You are a YouTube Shorts researcher for a channel about RARE, CREEPY, and OBSCURE historical facts.

Below are {len(candidates)} topic candidates from various sources. Score each on these criteria (1-10):
- **Obscurity**: How unknown is this to the average person? (generic = 1, never heard of = 10)
- **Creepiness**: How eerie, dark, or unsettling? (mundane = 1, nightmare fuel = 10)
- **Hook potential**: Can this grab attention in 2 seconds? (boring = 1, jaw-dropping = 10)
- **Shareability**: Would someone send this to a friend? (forgettable = 1, "you HAVE to see this" = 10)

CANDIDATES:
{candidate_text}

RULES:
- REJECT generic topics (World Wars, well-known events, famous people doing famous things)
- PREFER: forgotten events, eerie coincidences, dark practices, unsolved mysteries, cursed places
- The winning topic must work as a 45-60 second YouTube Short

IMPORTANT: You MUST respond with ONLY a JSON object. No analysis, no thinking, no markdown, no explanation. Just the raw JSON object:
{{
  "winner_index": <int>,
  "topic_title": "<catchy title for the Short>",
  "topic_summary": "<2-3 sentence summary with key facts to research further>",
  "scores": {{
    "obscurity": <int>,
    "creepiness": <int>,
    "hook_potential": <int>,
    "shareability": <int>,
    "total": <int>
  }},
  "rejection_reason_for_others": "<why the other top candidates lost>"
}}"""

    openrouter_models = [
        "google/gemma-4-31b-it:free",
        "minimax/minimax-m2.5:free",
        "google/gemma-4-26b-a4b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "openai/gpt-oss-120b:free",
        "google/gemma-3-27b-it:free",
        "qwen/qwen3-coder:free",
    ]

    # Try Gemini first (higher free-tier limits), then OpenRouter
    content = _call_gemini_raw(prompt)

    if not content:
        for model in openrouter_models:
            try:
                payload = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.7,
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
                content = data["choices"][0]["message"]["content"].strip()
                print(f"[TopicFetcher] AI scoring succeeded with OpenRouter: {model}")
                break
            except Exception as e:
                print(f"[TopicFetcher] OpenRouter {model} failed: {e}")
                continue

    if not content:
        print("[TopicFetcher] All AI models rate-limited. Using keyword-based fallback scorer.")
        return _keyword_score_and_pick(candidates)

    try:
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
        else:
            raise ValueError(f"No JSON found in AI response: {content[:200]}")

        winner_idx = result.get("winner_index", 0)
        if winner_idx < 0 or winner_idx >= len(candidates):
            winner_idx = 0

        return {
            "topic_title": result.get("topic_title", candidates[winner_idx]["title"]),
            "topic_summary": result.get("topic_summary", candidates[winner_idx]["content"]),
            "scores": result.get("scores", {}),
            "source": candidates[winner_idx]["source"],
            "source_url": candidates[winner_idx].get("url", ""),
            "rejection_reason": result.get("rejection_reason_for_others", ""),
        }
    except Exception as e:
        print(f"[TopicFetcher] AI scoring failed: {e}")
        # Fallback: pick a random candidate
        pick = random.choice(candidates)
        return {
            "topic_title": pick["title"],
            "topic_summary": pick["content"],
            "scores": {},
            "source": pick["source"],
            "source_url": pick.get("url", ""),
            "rejection_reason": "AI scoring failed, random pick",
        }


def fetch_topic(used_topics_file: Path | None = None) -> dict:
    """Main entry point: run all research layers, score, return best topic."""
    print("[TopicFetcher] Starting triple-layer research...")

    # Load used topics for dedup
    used_topics = set()
    if used_topics_file and used_topics_file.exists():
        used_topics = set(used_topics_file.read_text().strip().splitlines())

    client = TavilyClient(api_key=TAVILY_API_KEY)

    # Layer 1: Reddit via Tavily
    print("[TopicFetcher] Layer 1 — Searching Reddit via Tavily...")
    reddit_candidates = fetch_reddit_via_tavily(client)
    print(f"  Found {len(reddit_candidates)} Reddit candidates")

    # Layer 2: Wikipedia
    print("[TopicFetcher] Layer 2 — Wikipedia On This Day + obscure search...")
    wiki_otd = fetch_wikipedia_on_this_day()
    wiki_search = fetch_wikipedia_random_obscure()
    wiki_candidates = wiki_otd + wiki_search
    print(f"  Found {len(wiki_candidates)} Wikipedia candidates")

    # Layer 3: General web via Tavily
    print("[TopicFetcher] Layer 3 — General web search via Tavily...")
    web_candidates = fetch_web_via_tavily(client)
    print(f"  Found {len(web_candidates)} web candidates")

    # Combine all candidates
    all_candidates = reddit_candidates + wiki_candidates + web_candidates

    # Dedup against used topics
    if used_topics:
        all_candidates = [
            c for c in all_candidates
            if c["title"].lower().strip() not in used_topics
        ]

    print(f"[TopicFetcher] Total unique candidates: {len(all_candidates)}")

    if not all_candidates:
        raise ValueError("No topic candidates found from any layer")

    # Cap at 15 candidates for AI scoring (avoid token bloat)
    if len(all_candidates) > 15:
        all_candidates = random.sample(all_candidates, 15)

    # AI scoring
    print("[TopicFetcher] Scoring candidates with AI...")
    best = score_and_pick_best(all_candidates)

    print(f"[TopicFetcher] Winner: {best['topic_title']}")
    print(f"  Source: {best['source']}")
    print(f"  Scores: {best.get('scores', {})}")

    return best


if __name__ == "__main__":
    result = fetch_topic()
    print("\n" + "=" * 60)
    print(f"TOPIC: {result['topic_title']}")
    print(f"SUMMARY: {result['topic_summary']}")
    print(f"SOURCE: {result['source']}")
    print(f"SCORES: {json.dumps(result.get('scores', {}), indent=2)}")
