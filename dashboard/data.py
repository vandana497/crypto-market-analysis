"""
Data access layer for the dashboard. Keeps SQL separate from layout/callback
code so the queries can be tested independently of Dash.

All functions return pandas DataFrames, pulled fresh from MySQL on each call
(no caching) - fine for a portfolio project's data volume, and means the
dashboard always reflects the latest curated data without a restart.
"""

import pandas as pd
from sqlalchemy import text

from src.db import get_engine

# Excludes the one-off test day so it doesn't skew any chart.
MIN_DATE = "2026-08-18"


def get_latest_date() -> str:
    query = text("SELECT MAX(summary_date) AS d FROM curated_daily_summary")
    with get_engine().connect() as conn:
        result = conn.execute(query).fetchone()
    return str(result[0]) if result and result[0] else MIN_DATE


def get_top_movers(target_date: str, direction: str = "gainers", limit: int = 10) -> pd.DataFrame:
    order = "DESC" if direction == "gainers" else "ASC"
    query = text(f"""
        SELECT name, symbol, open_price, close_price, pct_change_intraday, snapshot_count
        FROM curated_daily_summary
        WHERE summary_date = :target_date
        ORDER BY pct_change_intraday {order}
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"target_date": target_date, "limit": limit})


def get_volatility_leaderboard(limit: int = 15) -> pd.DataFrame:
    query = text("""
        SELECT
            name, symbol,
            ROUND(AVG(volatility), 4) AS avg_volatility,
            ROUND(AVG((open_price + close_price) / 2), 4) AS avg_price,
            ROUND(AVG(volatility) / AVG((open_price + close_price) / 2) * 100, 4) AS volatility_pct_of_price,
            COUNT(*) AS days_tracked
        FROM curated_daily_summary
        WHERE summary_date >= :min_date
        GROUP BY coin_id, name, symbol
        HAVING days_tracked >= 3
        ORDER BY volatility_pct_of_price DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"min_date": MIN_DATE, "limit": limit})


def get_consistent_movers(limit: int = 15) -> pd.DataFrame:
    query = text("""
        SELECT name, symbol, COUNT(*) AS days_in_top10, ROUND(AVG(pct_change_intraday), 4) AS avg_pct_change
        FROM (
            SELECT *, RANK() OVER (
                PARTITION BY summary_date ORDER BY ABS(pct_change_intraday) DESC
            ) AS daily_rank
            FROM curated_daily_summary
            WHERE summary_date >= :min_date
        ) ranked
        WHERE daily_rank <= 10
        GROUP BY coin_id, name, symbol
        HAVING days_in_top10 >= 2
        ORDER BY days_in_top10 DESC, avg_pct_change DESC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"min_date": MIN_DATE, "limit": limit})


def get_market_cap_trend(top_n: int = 10) -> pd.DataFrame:
    query = text("""
        SELECT summary_date, name, symbol, avg_market_cap
        FROM curated_daily_summary
        WHERE coin_id IN (
            SELECT coin_id FROM (
                SELECT coin_id FROM curated_daily_summary
                WHERE summary_date = (SELECT MAX(summary_date) FROM curated_daily_summary)
                ORDER BY avg_market_cap DESC
                LIMIT :top_n
            ) AS top_coins
        )
        AND summary_date >= :min_date
        ORDER BY name, summary_date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"top_n": top_n, "min_date": MIN_DATE})


def get_pipeline_health() -> pd.DataFrame:
    query = text("""
        SELECT run_type, status, COUNT(*) AS run_count,
               MAX(finished_at) AS last_run
        FROM pipeline_runs
        GROUP BY run_type, status
        ORDER BY run_type, status
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn)


def get_data_completeness() -> pd.DataFrame:
    query = text("""
        SELECT summary_date, COUNT(*) AS coins_tracked, AVG(snapshot_count) AS avg_snapshots
        FROM curated_daily_summary
        WHERE summary_date >= :min_date
        GROUP BY summary_date
        ORDER BY summary_date
    """)
    with get_engine().connect() as conn:
        return pd.read_sql(query, conn, params={"min_date": MIN_DATE})
