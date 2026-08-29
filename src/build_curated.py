"""
Builds curated_daily_summary from staging_crypto.

This is a pure SQL aggregation (open/close/min/max/volatility per coin per day)
rather than pulling everything into pandas — lets MySQL do what it's good at,
and means the curated table stays small and fast for the dashboard to query.

open/close are approximated as the first/last snapshot price of the day,
which is standard OHLC logic.
"""

from sqlalchemy import text

from src.db import get_engine
from src.logger import get_logger
import pandas as pd

logger = get_logger()

BUILD_SQL = text(
    """
    INSERT INTO curated_daily_summary
        (summary_date, coin_id, name, symbol, open_price, close_price,
         min_price, max_price, avg_market_cap, pct_change_intraday,
         volatility, snapshot_count)
    SELECT
        summary_date, coin_id, name, symbol,
        open_price, close_price, min_price, max_price,
        avg_market_cap, NULL AS pct_change_intraday, volatility, snapshot_count
    FROM (
        SELECT
            DATE(snapshot_time) AS summary_date,
            coin_id,
            name,
            symbol,
            FIRST_VALUE(price_usd) OVER (
                PARTITION BY coin_id, DATE(snapshot_time)
                ORDER BY snapshot_time ASC
            ) AS open_price,
            FIRST_VALUE(price_usd) OVER (
                PARTITION BY coin_id, DATE(snapshot_time)
                ORDER BY snapshot_time DESC
            ) AS close_price,
            MIN(price_usd) OVER (PARTITION BY coin_id, DATE(snapshot_time)) AS min_price,
            MAX(price_usd) OVER (PARTITION BY coin_id, DATE(snapshot_time)) AS max_price,
            AVG(market_cap) OVER (PARTITION BY coin_id, DATE(snapshot_time)) AS avg_market_cap,
            STDDEV(price_usd) OVER (PARTITION BY coin_id, DATE(snapshot_time)) AS volatility,
            COUNT(*) OVER (PARTITION BY coin_id, DATE(snapshot_time)) AS snapshot_count,
            ROW_NUMBER() OVER (
                PARTITION BY coin_id, DATE(snapshot_time)
                ORDER BY snapshot_time ASC
            ) AS rn
        FROM staging_crypto
        WHERE DATE(snapshot_time) = :target_date
    ) windowed
    WHERE rn = 1   -- one row per coin per day, window functions already aggregated
    ON DUPLICATE KEY UPDATE
        open_price = VALUES(open_price),
        close_price = VALUES(close_price),
        min_price = VALUES(min_price),
        max_price = VALUES(max_price),
        avg_market_cap = VALUES(avg_market_cap),
        volatility = VALUES(volatility),
        snapshot_count = VALUES(snapshot_count)
    """
)

UPDATE_PCT_CHANGE_SQL = text(
    """
    UPDATE curated_daily_summary
    SET pct_change_intraday = ROUND(
        (close_price - open_price) / open_price * 100, 4
    )
    WHERE summary_date = :target_date AND open_price > 0
    """
)


def build_curated_daily(target_date: str | None = None) -> None:
    """
    target_date: 'YYYY-MM-DD' string. Defaults to today (UTC).
    Safe to re-run for the same date — upserts, doesn't duplicate.
    """
    if target_date is None:
        target_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(BUILD_SQL, {"target_date": target_date})
        conn.execute(UPDATE_PCT_CHANGE_SQL, {"target_date": target_date})

    logger.info(f"Curated daily summary built for {target_date}.")


if __name__ == "__main__":
    build_curated_daily()
