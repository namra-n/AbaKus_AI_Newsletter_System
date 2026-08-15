"""
llm_pipeline.py
The content-selection brain of the system. For every candidate article:
  1. Score relevance to MBA students on 4 axes (0-10 each)
  2. Drop anything below RELEVANCE_THRESHOLD
  3. Generate a structured summary (what happened / why MBAs should care /
     one number that matters)
  4. Tag with 0+ interest segments (Finance, Consulting, Marketing, ...)

All four steps happen in a single batched LLM call per article batch to
keep API cost and latency low. If no GEMINI_API_KEY is configured
(MOCK_MODE), a deterministic offline heuristic stands in, so the rest of
the pipeline (formatting, delivery, automation) can be built and tested
without spending API quota.
"""

import json
import re

import requests

from config import (
    GEMINI_API_KEY,
    GEMINI_API_URL,
    MOCK_MODE,
    RELEVANCE_THRESHOLD,
    INTEREST_SEGMENTS,
)

SYSTEM_PROMPT = f"""You are the content-selection editor for an AI/tech newsletter aimed at MBA
students at a top Indian business school. For each article you are given (title + source summary),
you must:

1. Score relevance 0-10 on each of these four axes:
   - business_impact: does this change how companies compete or operate?
   - career_relevance: is this a tool/trend recruiters or case interviews would reference?
   - case_study_potential: could this become a class discussion point or CV line?
   - novelty: is this genuinely new information, not a rehash of old news?

2. Write a structured summary with exactly these three parts:
   - what_happened: 2 sentences, plain language, no jargon
   - why_mba_should_care: 1-2 sentences connecting it to business strategy, careers, or markets
   - key_number: one concrete figure from the article (funding amount, %, market size, user count).
     If genuinely no number exists, use null.

3. Tag the article with any of these interest segments that apply (can be multiple, or empty list):
   {INTEREST_SEGMENTS}

Return ONLY a JSON array, one object per article, in the same order as given, with this exact shape:
[{{
  "id": "<article id>",
  "scores": {{"business_impact": 0-10, "career_relevance": 0-10, "case_study_potential": 0-10, "novelty": 0-10}},
  "what_happened": "...",
  "why_mba_should_care": "...",
  "key_number": "..." or null,
  "tags": ["Finance", ...]
}}]

No preamble, no markdown fences, no commentary — JSON only.
"""


def _composite_score(scores: dict) -> float:
    return sum(scores.values()) / len(scores)


# ---------------------------------------------------------------------------
# Live path (real Gemini API call, free tier)
# ---------------------------------------------------------------------------
def _call_llm(articles: list[dict]) -> list[dict]:
    payload = [{"id": a["id"], "title": a["title"], "summary": a["raw_summary"]} for a in articles]

    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload)}]}],
        # Forces the model to return valid JSON directly — no markdown
        # fences to strip, no "here is the JSON:" preamble to parse around.
        "generationConfig": {"response_mime_type": "application/json"},
    }

    resp = requests.post(
        GEMINI_API_URL,
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Offline heuristic fallback (MOCK_MODE) — deterministic, no network needed.
# Lets the rest of the system be built/tested/demoed without an API key.
# ---------------------------------------------------------------------------
_BUSINESS_KEYWORDS = {
    "funding": 3, "raises": 3, "valuation": 3, "acquires": 3, "acquisition": 3,
    "ipo": 3, "revenue": 2, "market": 2, "enterprise": 2, "startup": 2,
    "layoffs": 2, "ceo": 2, "strategy": 2, "regulation": 2, "policy": 2,
}
_CAREER_KEYWORDS = {
    "hiring": 3, "jobs": 3, "skills": 2, "tool": 2, "productivity": 2,
    "copilot": 2, "workflow": 2, "automation": 2,
}


def _keyword_score(text: str, keywords: dict, base: float) -> float:
    text_l = text.lower()
    bump = sum(v for k, v in keywords.items() if k in text_l)
    return min(10.0, base + bump)


def _mock_score_and_summarize(article: dict) -> dict:
    text = f"{article['title']} {article['raw_summary']}"
    business = _keyword_score(text, _BUSINESS_KEYWORDS, base=5.0)
    career = _keyword_score(text, _CAREER_KEYWORDS, base=5.0)
    case_study = min(10.0, (business + career) / 2 + 0.5)
    novelty = 7.0  # assume fresh since it just came off the feed

    tag_keywords = {
        "Finance": ["funding", "raises", "valuation", "revenue", "ipo", "series a",
                    "series b", "series c", "salaries", "compensation"],
        "Consulting": ["strategy", "competitive", "consulting", "case stud", "pricing model"],
        "Marketing": ["brand", "campaign", "advertis", "creative agenc"],
        "Product": ["launch", "feature", "app", "release", "rolled out", "assistant"],
        "Analytics": ["benchmark", "algorithm", "simulation", "compute", "survey found",
                      "report found", "adoption"],
    }
    text_l = text.lower()
    tag_hits = {tag: sum(1 for kw in kws if kw in text_l) for tag, kws in tag_keywords.items()}
    ranked = sorted([(t, h) for t, h in tag_hits.items() if h > 0], key=lambda x: -x[1])
    tags = [t for t, _ in ranked[:2]] or ["General"]

    sentences = re.split(r"(?<=[.!?])\s+", article["raw_summary"])
    what_happened = " ".join(sentences[:2]) or article["title"]

    return {
        "id": article["id"],
        "scores": {
            "business_impact": round(business, 1),
            "career_relevance": round(career, 1),
            "case_study_potential": round(case_study, 1),
            "novelty": round(novelty, 1),
        },
        "what_happened": what_happened,
        "why_mba_should_care": (
            "This signals a shift worth tracking for anyone evaluating tech-sector "
            "strategy, career moves, or investment theses in AI."
        ),
        "key_number": None,
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def score_and_summarize(articles: list[dict], batch_size: int = 15) -> list[dict]:
    """Runs relevance scoring + summarization + tagging over all articles,
    filters by RELEVANCE_THRESHOLD, and returns enriched article dicts
    sorted by composite score (best first)."""
    if not articles:
        return []

    results_by_id = {}
    if MOCK_MODE:
        for a in articles:
            results_by_id[a["id"]] = _mock_score_and_summarize(a)
    else:
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            try:
                for r in _call_llm(batch):
                    results_by_id[r["id"]] = r
            except Exception as exc:  # noqa: BLE001
                # Billing issues, rate limits, or transient API outages
                # shouldn't take down the whole run — degrade to the
                # offline heuristic for this batch so subscribers still
                # get an issue, and surface the problem loudly in logs.
                print(f"[llm_pipeline] WARNING: live LLM call failed ({exc}); "
                      f"falling back to offline scoring for this batch.")
                for a in batch:
                    results_by_id[a["id"]] = _mock_score_and_summarize(a)

    enriched = []
    for a in articles:
        r = results_by_id.get(a["id"])
        if not r:
            continue
        composite = _composite_score(r["scores"])
        if composite < RELEVANCE_THRESHOLD:
            continue
        enriched.append({
            **a,
            **r,
            "composite_score": round(composite, 2),
        })

    enriched.sort(key=lambda x: x["composite_score"], reverse=True)
    return enriched


if __name__ == "__main__":
    sample = [{
        "id": "test1",
        "title": "Startup raises $50M to build AI copilots for enterprise sales teams",
        "raw_summary": "The company says its tool cuts sales-prep time by 40% and has "
                        "signed several Fortune 500 pilots this quarter.",
        "source": "TechCrunch AI",
        "link": "https://example.com",
        "published": "",
    }]
    print(json.dumps(score_and_summarize(sample), indent=2))
