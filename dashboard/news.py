"""
Live news + sentiment matching for today's top movers - now using Currents API.

Why the switch from cryptocurrency.cv:
- Its /api/news free tier, despite marketing 2,655+ articles, only actually
  served a handful of unrelated regulatory articles in practice - not
  usable for real coin-specific matching.
- NewsAPI.org's free tier explicitly forbids production/live-domain use
  (localhost only) - would break the moment it hit our deployed Render URL.
- Currents API's free tier (250 req/day) explicitly permits production use
  and returns genuinely relevant, real-outlet crypto articles when searched
  by keyword - confirmed via live test before building this.

Design:
- One search call per coin (keywords=<coin name>), not a single bulk pull -
  Currents' /v1/search is keyword-driven, unlike the old bulk-feed approach.
- Sentiment analysis still runs entirely offline via VADER - no added cost.
- Scoped to today's top movers only (live/current), same as before.
"""

import logging
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config.settings import CURRENTS_API_KEY

logger = logging.getLogger("crypto_pipeline")

SEARCH_URL = "https://api.currentsapi.services/v1/search"
REQUEST_TIMEOUT = 10

_analyzer = SentimentIntensityAnalyzer()


def fetch_news_for_coin(coin_name: str, page_size: int = 5) -> list[dict]:
    """
    Searches Currents API directly by coin name - one call per coin, since
    the search endpoint is keyword-driven (unlike a bulk feed we'd filter
    client-side). Returns an empty list on any failure or missing key, so
    a news problem never breaks the rest of the dashboard.
    """
    if not CURRENTS_API_KEY:
        logger.warning("CURRENTS_API_KEY not set - skipping news fetch.")
        return []

    try:
        response = requests.get(
            SEARCH_URL,
            params={
                "keywords": coin_name,
                "language": "en",
                "page_size": page_size,
                "apiKey": CURRENTS_API_KEY,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("news", [])
    except Exception as e:
        logger.warning(f"News fetch failed for {coin_name}: {e}")
        return []


def score_sentiment(text: str) -> dict:
    """
    VADER compound score (-1 to +1) plus label, using VADER's own documented
    standard thresholds (>=0.05 positive, <=-0.05 negative, else neutral).
    """
    scores = _analyzer.polarity_scores(text or "")
    compound = scores["compound"]
    if compound >= 0.05:
        label = "Positive"
    elif compound <= -0.05:
        label = "Negative"
    else:
        label = "Neutral"
    return {"compound": compound, "label": label}


def get_news_with_sentiment_for_coin(coin_name: str, symbol: str) -> dict:
    """
    Full pipeline for one coin: search Currents API by name, score each
    result's sentiment, return an aggregate. This is what the dashboard
    tab calls, once per coin shown.
    """
    articles = fetch_news_for_coin(coin_name)

    scored_articles = []
    for article in articles:
        sentiment = score_sentiment(f"{article.get('title', '')}. {article.get('description', '')}")
        scored_articles.append({
            "title": article.get("title"),
            "link": article.get("url"),
            "source": article.get("author") or "Unknown",
            "pubDate": article.get("published"),
            "sentiment_label": sentiment["label"],
            "sentiment_score": sentiment["compound"],
        })

    if scored_articles:
        avg_compound = sum(a["sentiment_score"] for a in scored_articles) / len(scored_articles)
        overall_label = "Positive" if avg_compound >= 0.05 else "Negative" if avg_compound <= -0.05 else "Neutral"
    else:
        avg_compound = None
        overall_label = "No coverage found"

    return {
        "coin_name": coin_name,
        "symbol": symbol,
        "articles": scored_articles,
        "overall_sentiment": overall_label,
        "overall_score": avg_compound,
    }
