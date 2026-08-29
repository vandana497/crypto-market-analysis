"""
Entry point. Runs the fetch cycle on a schedule, spaced to stay within
the free-tier daily call budget (333/day -> ~1 call every 4.3 minutes).

Usage:
    python run.py            # runs continuously, respecting INTERVAL_SECONDS
    python run.py --once     # runs a single cycle and exits (useful for cron/Airflow later)
"""

import argparse
import time

from config.settings import CALLS_PER_DAY, INTERVAL_SECONDS
from src.fetch import run_once
from src.logger import get_logger

logger = get_logger()


def _sync_to_mysql():
    """Loads the latest raw CSV into staging, then rebuilds today's curated summary."""
    from src.load_staging import load_staging
    from src.build_curated import build_curated_daily

    try:
        load_staging()
        build_curated_daily()
    except Exception as e:
        # a MySQL hiccup shouldn't kill the fetch loop - raw CSV already has the data safely
        logger.error(f"MySQL sync failed, will retry next cycle: {e}")


def main(run_forever: bool = True, sync_db: bool = False):
    logger.info(
        f"Starting pipeline: {CALLS_PER_DAY} calls/day, "
        f"~{INTERVAL_SECONDS}s between calls. DB sync: {sync_db}"
    )

    if not run_forever:
        run_once()
        if sync_db:
            _sync_to_mysql()
        return

    call_count = 0
    while True:
        run_once()
        call_count += 1
        if sync_db:
            _sync_to_mysql()
        logger.info(f"Completed call {call_count}. Sleeping {INTERVAL_SECONDS}s.")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="Run a single fetch cycle and exit."
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        help="After each fetch, also load raw data into MySQL staging + curated tables.",
    )
    args = parser.parse_args()
    main(run_forever=not args.once, sync_db=args.load_db)
