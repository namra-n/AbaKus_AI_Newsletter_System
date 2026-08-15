"""
fetcher.py
Pulls live articles from all configured RSS/Atom sources, normalizes them
into a common shape, filters to recent items, and removes duplicates.

Deliberately built on `requests` + the standard-library XML parser rather
than feedparser: fewer dependencies to break in CI, full control over
timeouts/retries/headers (several publishers reject requests with no
User-Agent or block bare feedparser fetches), and it's easy to read/debug
when a feed misbehaves.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from config import RSS_SOURCES, MAX_ARTICLES_PER_SOURCE, SEND_HISTORY_FILE

REQUEST_TIMEOUT = 10          # seconds, per source
MAX_RETRIES = 2
FRESHNESS_WINDOW_DAYS = 10    # ignore articles older than this
USER_AGENT = (
    "AbaKusNewsletterBot/1.0 (+https://iimk.ac.in; contact: abakus@iimk.ac.in) "
    "python-requests"
)

# Atom feeds use a namespaced <entry>/<link>/<summary> instead of RSS's
# unnamespaced <item>/<link>/<description>.
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _clean_html(raw: str) -> str:
    """Strip tags/whitespace noise from feed summary fields."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _article_id(title: str, link: str) -> str:
    """Stable hash used for deduplication and send-history tracking."""
    key = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _parse_date(raw: str):
    """Feeds mix RFC-822 (RSS) and ISO-8601 (Atom) dates — try both, and
    treat an unparseable date as 'unknown' rather than failing the item."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_fresh(published_dt, window_days: int = FRESHNESS_WINDOW_DAYS) -> bool:
    if published_dt is None:
        return True  # unknown date: don't discard, just can't freshness-filter it
    if published_dt.tzinfo is None:
        published_dt = published_dt.replace(tzinfo=timezone.utc)
    return published_dt >= datetime.now(timezone.utc) - timedelta(days=window_days)


def _fetch_raw(url: str) -> bytes:
    """GET with retries and a real User-Agent — plain requests with no UA
    or timeout is what gets a feed fetch silently 403'd or hung
    indefinitely in production."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, */*"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            last_exc = exc
    raise last_exc


def _parse_rss_or_atom(content: bytes) -> list[dict]:
    """Returns raw entries as dicts with title/link/summary/published,
    handling both RSS 2.0 <item> and Atom <entry> shapes."""
    root = ET.fromstring(content)
    entries = []

    items = root.findall(".//item")  # RSS
    if items:
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = item.findtext("description") or item.findtext("summary") or ""
            published = item.findtext("pubDate") or item.findtext("published") or ""
            entries.append({"title": title, "link": link, "summary": summary, "published": published})
        return entries

    atom_entries = root.findall(".//atom:entry", ATOM_NS)  # Atom
    for entry in atom_entries:
        title = (entry.findtext("atom:title", namespaces=ATOM_NS) or "").strip()
        link_el = entry.find("atom:link", ATOM_NS)
        link = link_el.get("href", "").strip() if link_el is not None else ""
        summary = (
            entry.findtext("atom:summary", namespaces=ATOM_NS)
            or entry.findtext("atom:content", namespaces=ATOM_NS)
            or ""
        )
        published = (
            entry.findtext("atom:published", namespaces=ATOM_NS)
            or entry.findtext("atom:updated", namespaces=ATOM_NS)
            or ""
        )
        entries.append({"title": title, "link": link, "summary": summary, "published": published})
    return entries


def fetch_source(source: dict, max_items: int = MAX_ARTICLES_PER_SOURCE) -> list[dict]:
    """Fetch, parse, freshness-filter, and normalize entries from a single
    feed URL. Raises on network/parse failure — callers should catch this
    per-source so one dead feed doesn't kill the whole run."""
    raw = _fetch_raw(source["url"])
    raw_entries = _parse_rss_or_atom(raw)

    articles = []
    for entry in raw_entries:
        title, link = entry["title"], entry["link"]
        if not title or not link:
            continue

        published_dt = _parse_date(entry["published"])
        if not _is_fresh(published_dt):
            continue

        articles.append({
            "id": _article_id(title, link),
            "title": title,
            "link": link,
            "raw_summary": _clean_html(entry["summary"])[:1200],
            "source": source["name"],
            "published": entry["published"],
        })
        if len(articles) >= max_items:
            break
    return articles


def fetch_all(sources: list[dict] = RSS_SOURCES) -> list[dict]:
    """Fetch from every configured source. Failures on one source don't
    block the others — a dead feed shouldn't kill the whole run."""
    all_articles = []
    for source in sources:
        try:
            found = fetch_source(source)
            all_articles.extend(found)
            print(f"[fetcher] {source['name']}: {len(found)} fresh articles")
        except Exception as exc:  # noqa: BLE001 - log and continue
            print(f"[fetcher] WARNING: failed to fetch '{source['name']}': {exc}")
    return all_articles


def _load_send_history() -> set[str]:
    if not os.path.exists(SEND_HISTORY_FILE):
        return set()
    with open(SEND_HISTORY_FILE) as f:
        history = json.load(f)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    return {a_id for a_id, sent_at in history.items() if sent_at >= cutoff}


def dedupe(articles: list[dict]) -> list[dict]:
    """Remove within-run duplicates (same story, multiple feeds) and
    articles already sent in a previous issue."""
    seen_titles = set()
    already_sent = _load_send_history()
    deduped = []
    for a in articles:
        title_key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:60]
        if title_key in seen_titles:
            continue
        if a["id"] in already_sent:
            continue
        seen_titles.add(title_key)
        deduped.append(a)
    return deduped


def load_demo_articles(path: str = "sample_data/mock_articles.json") -> list[dict]:
    """Loads bundled sample articles instead of hitting live feeds — used
    for local testing, demos, and CI dry-runs without network access."""
    with open(path) as f:
        return json.load(f)


def fetch_and_dedupe(demo: bool = False) -> list[dict]:
    articles = load_demo_articles() if demo else fetch_all()
    return dedupe(articles)


if __name__ == "__main__":
    results = fetch_and_dedupe()
    print(f"\nFetched {len(results)} unique, unseen, fresh articles.")
    for a in results[:5]:
        print(f"  - [{a['source']}] {a['title']}")
