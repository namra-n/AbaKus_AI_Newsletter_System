"""
Central configuration for the AI Newsletter Automation system.
Edit this file to add/remove sources, change categories, or tune thresholds.
"""

import os

# ---------------------------------------------------------------------------
# Sources (RSS feeds). Add as many as you like — the fetcher treats them all
# the same way regardless of type (news site, blog, curated newsletter).
# ---------------------------------------------------------------------------
RSS_SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
]

# Max articles pulled per source per run (keeps LLM cost bounded)
MAX_ARTICLES_PER_SOURCE = 8

# ---------------------------------------------------------------------------
# Interest segments students can subscribe to. Every article gets tagged
# with zero or more of these during summarization.
# ---------------------------------------------------------------------------
INTEREST_SEGMENTS = ["Finance", "Consulting", "Marketing", "Product", "Analytics", "General"]

# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------
# Each article is scored 0-10 on four axes (see llm_pipeline.py). Only
# articles with a composite average at or above this bar make the cut.
RELEVANCE_THRESHOLD = 6.0

# Hard cap on how many articles appear in a single issue, post-filtering.
MAX_ARTICLES_PER_ISSUE = 8

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
LLM_MODEL = "claude-sonnet-4-6"

# If no API key is present (e.g. running a local demo), the pipeline falls
# back to a deterministic offline heuristic so the rest of the system can
# still be exercised end-to-end without network access or billing.
MOCK_MODE = ANTHROPIC_API_KEY is None

# ---------------------------------------------------------------------------
# Storage (subscriber list + send history)
# ---------------------------------------------------------------------------
# For the reference implementation, a local CSV stands in for a Google
# Sheet — see README for how to swap in the Sheets API without touching
# any other module.
SUBSCRIBERS_FILE = "subscribers.csv"
SEND_HISTORY_FILE = "outputs/send_history.json"

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
FROM_NAME = "AbaKus AI Digest"

NEWSLETTER_TITLE = "The AbaKus AI Digest"
CLUB_NAME = "AbaKus — The Tech Club of IIM Kozhikode"
