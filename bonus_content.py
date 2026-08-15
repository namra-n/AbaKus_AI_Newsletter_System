"""
bonus_content.py
Generates the two "value-add" sections that make the newsletter feel like
more than a link dump:

  - AI Tool of the Week: a tool + a concrete MBA use case (not just a
    feature list — the point is "here's how to use this in a case prep
    or internship this week").
  - Startup Spotlight: pulled from the same article batch when a funding
    story is present, so it's always grounded in real news rather than
    a canned pick.

Both use the same MOCK_MODE / live-LLM split as llm_pipeline.py.
"""

import json
import re

from config import ANTHROPIC_API_KEY, LLM_MODEL, MOCK_MODE

# A rotating pool the "Tool of the Week" picks from when running in mock
# mode, or as a candidate list the live LLM call can choose/write about.
TOOL_POOL = [
    {"name": "NotebookLM", "category": "Research synthesis",
     "blurb": "Upload case PDFs, 10-Ks, or lecture notes and query them directly — "
              "useful for turning a stack of readings into a quick discussion brief."},
    {"name": "Perplexity Pro", "category": "Market research",
     "blurb": "Cited, up-to-date answers make it faster to sanity-check market-sizing "
              "numbers for a consulting case or business plan."},
    {"name": "Claude (Projects)", "category": "Structured analysis",
     "blurb": "Keep a persistent project with your case data and prior analysis so "
              "follow-up questions don't require re-explaining context every time."},
    {"name": "Gamma", "category": "Presentation drafting",
     "blurb": "Turns a rough outline into a formatted deck in minutes — handy for a "
              "first-draft client presentation before you polish the narrative."},
]


def get_tool_of_the_week(week_index: int) -> dict:
    """Deterministic rotation so the same tool isn't repeated back-to-back
    across consecutive runs."""
    return TOOL_POOL[week_index % len(TOOL_POOL)]


def get_startup_spotlight(articles: list[dict]) -> dict | None:
    """Picks the highest-scoring article that looks like a funding/startup
    story to feature as a standalone spotlight."""
    funding_kw = ["raises", "funding", "series a", "series b", "series c",
                  "valuation", "seed round", "acquires", "acquisition"]
    for a in articles:
        text = f"{a['title']} {a.get('raw_summary', '')}".lower()
        if any(k in text for k in funding_kw):
            return {
                "title": a["title"],
                "link": a["link"],
                "blurb": a.get("what_happened", a.get("raw_summary", ""))[:280],
            }
    return None


if __name__ == "__main__":
    print(json.dumps(get_tool_of_the_week(0), indent=2))
