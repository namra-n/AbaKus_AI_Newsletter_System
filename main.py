"""
main.py
Orchestrates the full weekly run:
  fetch -> dedupe -> score+summarize+tag -> personalize per subscriber
  -> format -> send -> log to send history

Run with:  python main.py
Env vars (see README): ANTHROPIC_API_KEY, SMTP_USER, SMTP_PASSWORD, ...
"""

import json
import os
import sys
from datetime import datetime, timezone

from config import SEND_HISTORY_FILE
from fetcher import fetch_and_dedupe
from llm_pipeline import score_and_summarize
from personalization import load_subscribers, personalize_for
from bonus_content import get_tool_of_the_week, get_startup_spotlight
from formatter import render_newsletter
from mailer import send_email


def _update_send_history(article_ids: list[str]) -> None:
    os.makedirs(os.path.dirname(SEND_HISTORY_FILE), exist_ok=True)
    history = {}
    if os.path.exists(SEND_HISTORY_FILE):
        with open(SEND_HISTORY_FILE) as f:
            history = json.load(f)
    now = datetime.now(timezone.utc).isoformat()
    for a_id in article_ids:
        history[a_id] = now
    with open(SEND_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def run(demo: bool = False) -> None:
    print("=" * 60)
    print(f"AbaKus AI Newsletter — weekly run starting{' [DEMO MODE]' if demo else ''}")
    print("=" * 60)

    # 1. Fetch + dedupe
    raw_articles = fetch_and_dedupe(demo=demo)
    print(f"[main] {len(raw_articles)} unique candidate articles after dedup")

    # 2. Score, summarize, tag, filter by relevance
    articles = score_and_summarize(raw_articles)
    print(f"[main] {len(articles)} articles passed the relevance bar")

    if not articles:
        print("[main] No qualifying articles this run — skipping send.")
        return

    # 3. Bonus content (shared across all subscribers this issue)
    week_index = datetime.now(timezone.utc).isocalendar().week
    tool_of_week = get_tool_of_the_week(week_index)
    startup_spotlight = get_startup_spotlight(articles)

    # 4. Personalize + format + send, per subscriber
    subscribers = load_subscribers()
    print(f"[main] Sending to {len(subscribers)} subscribers")

    for sub in subscribers:
        personal_articles = personalize_for(sub, articles)
        html = render_newsletter(sub, personal_articles, tool_of_week, startup_spotlight)
        send_email(sub["email"], html)

    # 5. Record what was sent so it isn't repeated next week
    _update_send_history([a["id"] for a in articles])

    print("[main] Run complete.")


if __name__ == "__main__":
    run(demo="--demo" in sys.argv)
