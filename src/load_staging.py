"""
Loads data from the raw CSV layer into the MySQL staging table.

Key design choices:
- Upsert via "INSERT ... ON DUPLICATE KEY UPDATE" so re-running this script
  on the same raw CSV is safe (idempotent) — no duplicate rows, matching
  the UNIQUE KEY(coin_id, snapshot_time) constraint in schema.sql.
- Every run is logged to pipeline_runs, regardless of success/failure —
  this is what lets a dashboard answer "did the last load succeed?"
- Column mapping from the CMC API's nested field names (quote.USD.price)
  to clean staging column names happens in one place.
"""

import pandas as pd
from sqlalchemy import text

from config.settings import RAW_CSV_PATH, STAGING_DATA_DIR
from src.db import get_engine
from src.logger import get_logger

logger = get_logger()

# Tracks how many raw CSV rows have already been loaded into staging, so
# each cycle only processes NEW rows instead of re-reading the whole file.
# This is what prevents the same row from being re-parsed (and potentially
# re-keyed differently, causing duplicates) on every single cycle.
PROCESSED_ROWS_MARKER = STAGING_DATA_DIR / ".rows_processed"

COLUMN_MAP = {
    "id": "coin_id",
    "name": "name",
    "symbol": "symbol",
    "quote.USD.price": "price_usd",
    "quote.USD.market_cap": "market_cap",
    "quote.USD.volume_24h": "volume_24h",
    "quote.USD.percent_change_1h": "percent_change_1h",
    "quote.USD.percent_change_24h": "percent_change_24h",
    "quote.USD.percent_change_7d": "percent_change_7d",
    "cmc_rank": "cmc_rank",
    "timestamp": "snapshot_time",
}

UPSERT_SQL = text(
    """
    INSERT INTO staging_crypto
        (coin_id, name, symbol, price_usd, market_cap, volume_24h,
         percent_change_1h, percent_change_24h, percent_change_7d,
         cmc_rank, snapshot_time)
    VALUES
        (:coin_id, :name, :symbol, :price_usd, :market_cap, :volume_24h,
         :percent_change_1h, :percent_change_24h, :percent_change_7d,
         :cmc_rank, :snapshot_time)
    ON DUPLICATE KEY UPDATE
        price_usd = VALUES(price_usd),
        market_cap = VALUES(market_cap),
        volume_24h = VALUES(volume_24h),
        percent_change_1h = VALUES(percent_change_1h),
        percent_change_24h = VALUES(percent_change_24h),
        percent_change_7d = VALUES(percent_change_7d),
        cmc_rank = VALUES(cmc_rank)
    """
)

LOG_RUN_SQL = text(
    """
    INSERT INTO pipeline_runs
        (run_type, status, rows_affected, error_message, started_at, finished_at)
    VALUES
        (:run_type, :status, :rows_affected, :error_message, :started_at, :finished_at)
    """
)


def _get_last_processed_count() -> int:
    if PROCESSED_ROWS_MARKER.exists():
        return int(PROCESSED_ROWS_MARKER.read_text().strip() or 0)
    return 0


def _set_last_processed_count(count: int) -> None:
    PROCESSED_ROWS_MARKER.write_text(str(count))


def _normalize_timestamp(ts):
    """
    Raw CSV may contain a mix of:
    - old rows: tz-aware UTC strings (from before the utcnow -> now fix)
    - new rows: naive local-time strings (after the fix)
    Strip any tz info so everything becomes a plain naive local timestamp.
    Old rows will be ~5:30h off from true local time - only affects a
    handful of legacy rows from before the fix.
    """
    parsed = pd.Timestamp(ts)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_localize(None)
    return parsed


def _load_and_clean_raw() -> pd.DataFrame:
    """
    Reads only the rows appended to the raw CSV since the last successful
    load (tracked via PROCESSED_ROWS_MARKER), instead of re-reading the
    entire file every cycle. This is both faster and safer: re-parsing
    the same row twice risks producing a slightly different snapshot_time
    if the parsing logic ever changes, which can silently create duplicate
    rows instead of updating the existing one.
    """
    last_count = _get_last_processed_count()
    full_df = pd.read_csv(RAW_CSV_PATH)

    if last_count >= len(full_df):
        return pd.DataFrame(columns=list(COLUMN_MAP.values()))  # nothing new

    df = full_df.iloc[last_count:].copy()
    new_total = len(full_df)

    missing = set(COLUMN_MAP.keys()) - set(df.columns)
    if missing:
        raise ValueError(f"Raw CSV missing expected columns: {missing}")

    df = df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)
    df["snapshot_time"] = pd.to_datetime(df["snapshot_time"].apply(_normalize_timestamp)).dt.floor("min")
    df = df.dropna(subset=["coin_id", "price_usd", "snapshot_time"])
    df = df.drop_duplicates(subset=["coin_id", "snapshot_time"])

    df.attrs["new_total_row_count"] = new_total  # stash so load_staging() can update the marker
    return df


def load_staging() -> int:
    """Loads raw CSV into staging_crypto. Returns rows affected. Logs the run either way."""
    started_at = pd.Timestamp.now()
    engine = get_engine()
    rows_affected = 0
    status = "success"
    error_message = None

    try:
        df = _load_and_clean_raw()
        records = df.to_dict(orient="records")

        if records:
            with engine.begin() as conn:
                for record in records:
                    conn.execute(UPSERT_SQL, record)
            rows_affected = len(records)
            _set_last_processed_count(df.attrs["new_total_row_count"])
            logger.info(f"Staging load complete: {rows_affected} new rows upserted.")
        else:
            logger.info("Staging load: no new rows since last run.")

    except Exception as e:
        status = "failure"
        error_message = str(e)
        logger.error(f"Staging load failed: {e}")

    finally:
        finished_at = pd.Timestamp.now()
        try:
            with get_engine().begin() as conn:
                conn.execute(
                    LOG_RUN_SQL,
                    {
                        "run_type": "staging_load",
                        "status": status,
                        "rows_affected": rows_affected,
                        "error_message": error_message,
                        "started_at": started_at.to_pydatetime(),
                        "finished_at": finished_at.to_pydatetime(),
                    },
                )
        except Exception as log_err:
            logger.error(f"Could not write to pipeline_runs: {log_err}")

    if status == "failure":
        raise RuntimeError(error_message)

    return rows_affected


if __name__ == "__main__":
    load_staging()
