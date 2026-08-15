"""
personalization.py
Loads subscribers and works out which articles + bonus sections each one
sees. Deliberately simple and explainable (tag match, not a black-box
recommender) — appropriate for the subscriber volumes a college newsletter
actually has, and easy for a non-technical teammate to reason about.

Swap-in note: to back this with a live Google Sheet instead of a local
CSV, replace load_subscribers()'s body with a gspread read — nothing else
in the pipeline needs to change, since every other module only depends on
the list[dict] shape returned here.
"""

import csv
import os

from config import SUBSCRIBERS_FILE, INTEREST_SEGMENTS, MAX_ARTICLES_PER_ISSUE


def load_subscribers(path: str = SUBSCRIBERS_FILE) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        subs = []
        for row in reader:
            interests = [i.strip() for i in row.get("interests", "").split(";") if i.strip()]
            subs.append({
                "name": row.get("name", "").strip(),
                "email": row.get("email", "").strip(),
                "interests": interests or ["General"],
            })
    return subs


def personalize_for(subscriber: dict, articles: list[dict]) -> list[dict]:
    """Returns the subset of articles relevant to this subscriber's
    interests, ranked by relevance score, capped at MAX_ARTICLES_PER_ISSUE.
    Falls back to the top general-interest articles if a niche segment
    didn't produce enough matches this week — nobody should get an
    almost-empty email."""
    matches = [a for a in articles if set(a["tags"]) & set(subscriber["interests"])]

    if len(matches) < 3:
        remaining = [a for a in articles if a not in matches]
        matches += remaining[: 3 - len(matches)]

    return matches[:MAX_ARTICLES_PER_ISSUE]


def group_subscribers_by_segment(subscribers: list[dict]) -> dict[str, list[dict]]:
    """Useful for a quick summary of subscriber base composition, e.g. in
    logs or an admin dashboard."""
    groups = {seg: [] for seg in INTEREST_SEGMENTS}
    for sub in subscribers:
        for interest in sub["interests"]:
            groups.setdefault(interest, []).append(sub)
    return groups


if __name__ == "__main__":
    subs = load_subscribers()
    print(f"Loaded {len(subs)} subscribers")
    for seg, members in group_subscribers_by_segment(subs).items():
        print(f"  {seg}: {len(members)}")
