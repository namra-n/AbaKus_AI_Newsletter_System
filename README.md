# AbaKus AI Newsletter — Reference Implementation

Automated, personalized AI/tech digest for IIM Kozhikode students. Full
framework rationale is in `AbaKus_AI_Newsletter_Framework.pdf`; this README
covers running and extending the code.

## Quickstart (no API keys needed)

```bash
pip install -r requirements.txt
python main.py --demo
```

This runs the full pipeline — fetch → relevance filter → summarize → tag →
personalize → format → "send" — using bundled sample articles
(`sample_data/mock_articles.json`) and a deterministic offline scorer, and
writes one personalized HTML file per subscriber to `outputs/dry_run/`.
Open any of them in a browser to see a real, working newsletter.

## Running for real

1. `export ANTHROPIC_API_KEY=sk-...` — enables live relevance scoring +
   summarization (Claude). Without this, the system silently falls back to
   the offline heuristic (`MOCK_MODE` in `config.py`) — useful for
   development, not for production quality.
2. `export SMTP_USER=you@gmail.com SMTP_PASSWORD=<app-password>` — enables
   real sending. Without these, emails are written to `outputs/dry_run/`
   instead of sent.
3. Edit `subscribers.csv` (or swap in Google Sheets — see below).
4. `python main.py`

## Project structure

```
config.py            All tunables: sources, thresholds, segments, LLM model
fetcher.py            Pulls + dedupes RSS articles (or loads demo data)
llm_pipeline.py        Relevance scoring, summarization, tagging (+ offline fallback)
bonus_content.py       AI Tool of the Week, Startup Spotlight
personalization.py     Subscriber loading + per-segment filtering
formatter.py            Renders the Jinja2 HTML template per subscriber
templates/newsletter_template.html   Email HTML/CSS
mailer.py               SMTP send (or dry-run to disk)
main.py                Orchestrates the full run
.github/workflows/newsletter.yml     Weekly cron automation
```

## Architecture and workflow

See the diagrams and full rationale in the framework document. In short:

`Sources → Aggregator (dedupe) → Relevance Filter (LLM) → Summarizer (LLM)
→ Personalization → Formatter → Email Delivery`, with an opens/clicks
feedback loop back into personalization.

## Content selection logic

Every article is scored 0–10 by the LLM on four axes — business impact,
career relevance, case-study potential, novelty — and only the average
above `RELEVANCE_THRESHOLD` (default 6.0, in `config.py`) survives. This
is the mechanism, not a keyword filter, so it generalizes to any topic
within AI/tech rather than needing a maintained keyword list.

## Personalization logic

Each article is tagged with 0+ interest segments during the same LLM call.
Each subscriber is filtered to articles matching their declared interests
(`subscribers.csv`), capped at `MAX_ARTICLES_PER_ISSUE`. If a niche segment
doesn't produce enough matches in a given week, the system tops up with
the best general articles so nobody gets a near-empty email.

## Swapping the subscriber store for Google Sheets

`personalization.load_subscribers()` returns `list[dict]` with `name`,
`email`, `interests`. To back it with a live Sheet instead of the CSV,
replace only that function's body with a `gspread` read — no other module
needs to change, since everything downstream only depends on that shape.

## Live fetching — how it works and how it was verified

`fetcher.py` pulls each source over HTTP with a real User-Agent, a 10s
timeout, and up to 2 retries, then parses RSS 2.0 *and* Atom (auto-detected)
using the standard library XML parser — no `feedparser` dependency, so
there's one less thing to break in CI. Two extra safeguards:

- **Freshness filter** — articles older than `FRESHNESS_WINDOW_DAYS`
  (default 10, in `fetcher.py`) are dropped, since some feeds serve stale
  cached entries.
- **Per-source isolation** — if one feed is down or returns malformed XML,
  that source is skipped with a logged warning; the run continues with
  whatever sources succeeded.

This sandbox has no outbound internet access, so live sites like
TechCrunch couldn't be hit directly here. To verify the fetch/parse logic
for real (not just in theory), I stood up a local test server serving a
crafted RSS feed and a crafted Atom feed — including a stale 2024 entry
and a malformed entry with no title — and pointed the actual, unmodified
`fetch_source()` at it. Result: it correctly returned only the fresh,
valid entries from both formats, and correctly logged-and-skipped a dead
4th source without failing the run. That test isn't included in the repo
(it depended on a local-only server), but the code path it exercised is
exactly what runs against `RSS_SOURCES` in `config.py`.

**Before the first real run:** open each feed URL in `config.py` in a
browser to confirm it's still valid — publishers occasionally change their
feed paths. `python fetcher.py` will fetch live and print what it found,
so it's the fastest way to sanity-check the source list without running
the full pipeline.

## Automation

`.github/workflows/newsletter.yml` runs the pipeline every Monday via
GitHub Actions cron (free tier) and commits the updated send history so
duplicate articles aren't repeated the following week. Trigger a manual
test run anytime from the Actions tab ("Run workflow").

Required repo secrets: `ANTHROPIC_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`.

## Cost notes

- Sources: RSS feeds, all free.
- Storage: Google Sheets or the bundled CSV — no database hosting cost.
- Scheduling: GitHub Actions free tier comfortably covers a weekly run.
- LLM: one batched call per run (all articles scored + summarized
  together), so cost scales with weekly article volume, not subscriber
  count.
- Email: free tiers of Brevo/Resend/Gmail cover a few hundred sends/week.

## Tools used

- **Claude (Anthropic API)** — relevance scoring, summarization, and
  interest tagging in `llm_pipeline.py`.
- **Claude (this conversation)** — used to design the framework, write and
  test this codebase, and generate the architecture diagrams.
