"""
Live news + sentiment matching for today's top movers.

Design notes:
- Uses cryptocurrency.cv's free /api/news endpoint (no key, no payment) -
  their /api/search endpoint requires a crypto micropayment (x402 protocol),
  so we deliberately avoid it and do our own matching client-side instead.
- Since the free feed only returns recent/latest headlines (not a searchable
  historical archive), this feature is scoped to "why is X moving right now"
  - i.e. matched against TODAY's flagged movers, not historical backfill.
- Sentiment analysis runs entirely offline via VADER (a lexicon-based model
  bundled with the vaderSentiment package - no external API call, no cost,
  no rate limit) rather than depending on a second paid/free-tier service.
"""

import logging
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger("crypto_pipeline")

NEWS_API_URL = "https://cryptocurrency.cv/api/news"
REQUEST_TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; crypto-dashboard/1.0)"}

_analyzer = SentimentIntensityAnalyzer()


def fetch_latest_news(limit: int = 100) -> list[dict]:
    """
    Pulls the latest headlines across all sources. Free endpoint, no key
    required. Returns an empty list (rather than raising) on any failure,
    so a news-fetch problem never breaks the rest of the dashboard.
    """
    try:
        response = requests.get(
            NEWS_API_URL,
            params={"limit": limit},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("articles", [])
    except Exception as e:
        logger.warning(f"News fetch failed, showing no news for this cycle: {e}")
        return []


def match_articles_to_coin(articles: list[dict], coin_name: str, symbol: str, max_matches: int = 5) -> list[dict]:
    """
    Simple, transparent substring matching - looks for the coin's full name
    or ticker symbol in the article title or description. Not fuzzy/semantic
    (that would need the paid search endpoint), but reliable and explainable.
    """
    name_lower = coin_name.lower()
    symbol_lower = symbol.lower()
    matches = []

    for article in articles:
        title = (article.get("title") or "").lower()
        description = (article.get("description") or "").lower()
        haystack = f"{title} {description}"

        # symbol matched as a whole word only, to avoid false positives like
        # "ADA" matching inside an unrelated word
        symbol_hit = f" {symbol_lower} " in f" {haystack} "
        name_hit = name_lower in haystack

        if name_hit or symbol_hit:
            matches.append(article)
        if len(matches) >= max_matches:
            break

    return matches


def score_sentiment(text: str) -> dict:
    """
    Returns VADER's compound score (-1 to +1) plus a human-readable label.
    Compound >= 0.05 -> positive, <= -0.05 -> negative, else neutral -
    these are VADER's own documented standard thresholds.
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


def get_news_with_sentiment_for_coin(articles: list[dict], coin_name: str, symbol: str) -> dict:
    """
    Full pipeline for one coin: match articles, score each headline's
    sentiment, and return an aggregate. This is what the dashboard tab calls.
    """
    matched = match_articles_to_coin(articles, coin_name, symbol)

    scored_articles = []
    for article in matched:
        sentiment = score_sentiment(f"{article.get('title', '')}. {article.get('description', '')}")
        scored_articles.append({
            "title": article.get("title"),
            "link": article.get("link"),
            "source": article.get("source"),
            "pubDate": article.get("pubDate"),
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
