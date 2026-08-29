"""
Handles a single API call to CoinMarketCap: request, retry, validate, save.

Compared to the original notebook, this adds:
1. Retries with exponential backoff on network/API failures instead of
   letting one bad call kill the whole day's loop.
2. Basic data validation before writing (schema + sanity checks) so a
   malformed response can't silently corrupt the dataset.
3. Structured logging instead of print().
4. No global variables - api_runner() returns a DataFrame instead of
   mutating a module-level df2.
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi
import pandas as pd

from config.settings import (
    CMC_API_KEY,
    CMC_BASE_URL,
    CONVERT_CURRENCY,
    LISTING_LIMIT,
    LISTING_START,
    MAX_RETRIES,
    RAW_CSV_PATH,
    RETRY_BACKOFF_SECONDS,
)
from src.logger import get_logger

logger = get_logger()


class FetchError(Exception):
    """Raised when the API call fails after all retries are exhausted."""


def _build_request() -> urllib.request.Request:
    params = urllib.parse.urlencode(
        {
            "start": LISTING_START,
            "limit": LISTING_LIMIT,
            "convert": CONVERT_CURRENCY,
        }
    )
    return urllib.request.Request(
        f"{CMC_BASE_URL}?{params}",
        headers={
            "Accept": "application/json",
            "X-CMC_PRO_API_KEY": CMC_API_KEY,
        },
    )


def _call_api() -> dict:
    """Single attempt at hitting the API. Raises on any failure."""
    context = ssl.create_default_context(cafile=certifi.where())
    request = _build_request()
    with urllib.request.urlopen(request, context=context, timeout=15) as response:
        return json.load(response)


def _validate(df: pd.DataFrame) -> None:
    """
    Basic data quality checks before we trust the response enough to save it.
    Raise loudly rather than writing bad rows into the dataset.
    """
    required_cols = {"name", "symbol", "quote.USD.price", "quote.USD.market_cap"}
    missing = required_cols - set(df.columns)
    if missing:
        raise FetchError(f"Response missing expected columns: {missing}")

    if df.empty:
        raise FetchError("API returned an empty listing.")

    if (df["quote.USD.price"] < 0).any():
        raise FetchError("Negative price detected in response - data integrity issue.")

    if df["quote.USD.market_cap"].isna().any():
        logger.warning("Some rows have null market_cap - keeping them but flagging.")


def fetch_once() -> pd.DataFrame:
    """
    Fetch one snapshot from the API with retry/backoff, validate it,
    and return it as a DataFrame with a timestamp column. Does not save.
    """
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = _call_api()
            df = pd.json_normalize(data["data"])
            df["timestamp"] = pd.Timestamp.now()
            _validate(df)
            logger.info(f"Fetched {len(df)} coins successfully (attempt {attempt}).")
            return df
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed ({e}). Retrying in {wait}s.")
            time.sleep(wait)
        except FetchError as e:
            # data-quality failures aren't worth retrying - the API is
            # responding, just with bad data
            logger.error(f"Validation failed: {e}")
            raise

    raise FetchError(f"All {MAX_RETRIES} attempts failed. Last error: {last_error}")


def save_raw(df: pd.DataFrame) -> None:
    """Append to the raw CSV layer. Immutable, untouched - every snapshot kept as-is."""
    file_exists = RAW_CSV_PATH.exists()
    df.to_csv(RAW_CSV_PATH, mode="a", header=not file_exists, index=False)
    logger.info(f"Saved {len(df)} rows to {RAW_CSV_PATH}")


def run_once() -> None:
    """One full cycle: fetch, validate, save. Never raises - logs and moves on."""
    try:
        df = fetch_once()
        save_raw(df)
    except FetchError as e:
        logger.error(f"Run failed, skipping this cycle: {e}")
