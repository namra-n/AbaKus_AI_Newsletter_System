"""
formatter.py
Renders the Jinja2 email template into a finished HTML string for a given
subscriber + their personalized article list + this week's bonus content.
"""

from datetime import date

from jinja2 import Environment, FileSystemLoader

from config import NEWSLETTER_TITLE, CLUB_NAME

_env = Environment(loader=FileSystemLoader("templates"))
_template = _env.get_template("newsletter_template.html")


def render_newsletter(
    subscriber: dict,
    articles: list[dict],
    tool_of_week: dict | None,
    startup_spotlight: dict | None,
    base_url: str = "https://abakus-iimk.example",
) -> str:
    read_time = max(2, round(len(articles) * 0.8))
    interests = ", ".join(subscriber["interests"])

    return _template.render(
        title=NEWSLETTER_TITLE,
        club_name=CLUB_NAME,
        issue_date=date.today().strftime("%B %d, %Y"),
        subscriber_name=subscriber["name"].split()[0] if subscriber["name"] else "there",
        interests=interests,
        article_count=len(articles),
        read_time=read_time,
        articles=articles,
        tool_of_week=tool_of_week,
        startup_spotlight=startup_spotlight,
        feedback_up_url=f"{base_url}/feedback?email={subscriber['email']}&vote=up",
        feedback_down_url=f"{base_url}/feedback?email={subscriber['email']}&vote=down",
        unsubscribe_url=f"{base_url}/unsubscribe?email={subscriber['email']}",
        preferences_url=f"{base_url}/preferences?email={subscriber['email']}",
    )
