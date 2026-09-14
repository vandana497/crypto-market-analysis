"""
Live news + sentiment matching for today's top movers - now using Currents API.
...
Relevance filtering:
Some coin names/symbols are common English words (NEAR, SUI, ATOM, ONDO) that
match plenty of totally unrelated articles via plain keyword search. To fix
this without losing recall on unambiguous names (Zcash, Bitcoin), we:
1. Search with the coin name PLUS a crypto-context term, not the bare name -
   narrows the search itself before results even come back.
2. Post-filter every result: require at least one crypto/finance context word
   to actually appear in the title or description. A "NEAR" article that
   never mentions crypto/blockchain/token/price anywhere gets dropped, even
   though it matched the search keyword.
"""

import logging
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config.settings import CURRENTS_API_KEY

logger = logging.getLogger("crypto_pipeline")

SEARCH_URL = "https://api.currentsapi.services/v1/search"
REQUEST_TIMEOUT = 10

_analyzer = SentimentIntensityAnalyzer()

# If any of these appear in the title or description, the article is treated
# as genuinely crypto-related. Deliberately broad so real crypto news (which
# might not literally say "crypto") still passes - e.g. "trading", "market",
# "exchange", "wallet" catch coverage that talks about price/trading without
# using the word "crypto" itself.
CRYPTO_CONTEXT_WORDS = [
    "crypto", "cryptocurrency", "blockchain", "token", "coin", "defi",
    "web3", "bitcoin", "ethereum", "altcoin", "trading", "exchange",
    "wallet", "market cap", "price", "rally", "surge", "plunge",
]


def _is_crypto_relevant(article: dict) -> bool:
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()
    return any(word in text for word in CRYPTO_CONTEXT_WORDS)


def fetch_news_for_coin(coin_name: str, page_size: int = 8) -> list[dict]:
    """
    Searches Currents API by coin name + a crypto-context term (rather than
    the bare name), then filters results for genuine crypto relevance. This
    two-step approach handles common-English-word coin names (NEAR, SUI,
    ATOM) without needing a manual exception list per coin.
    Returns an empty list on any failure or missing key, so a news problem
    never breaks the rest of the dashboard.
    """
    if not CURRENTS_API_KEY:
        logger.warning("CURRENTS_API_KEY not set - skipping news fetch.")
        return []

    try:
        response = requests.get(
            SEARCH_URL,
            params={
                "keywords": f"{coin_name} cryptocurrency",
                "language": "en",
                "page_size": page_size,
                "apiKey": CURRENTS_API_KEY,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        raw_articles = data.get("news", [])
        relevant = [a for a in raw_articles if _is_crypto_relevant(a)]
        return relevant
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
