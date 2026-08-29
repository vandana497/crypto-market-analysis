"""
Centralized configuration for the crypto market cap pipeline.

Why this file exists:
- No hardcoded API keys or Windows paths anywhere else in the codebase.
- One place to change limits, intervals, or paths.
- Uses pathlib so it works the same on Windows/Mac/Linux (your original
  notebook used a raw C:\\Users\\... path, which only ran on one machine).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env in project root if present

# --- API ---
CMC_API_KEY = os.getenv("CMC_API_KEY")
if not CMC_API_KEY:
    raise EnvironmentError(
        "CMC_API_KEY not set. Copy .env.example to .env and add your key."
    )

CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

# --- Request parameters ---
LISTING_START = "1"
LISTING_LIMIT = "50"      # bumped from 15 -> 50 for richer sector/coin coverage
CONVERT_CURRENCY = "USD"

# --- Scheduling ---
# Free-tier CMC plans allow ~333 calls/day. Spacing calls across the day
# instead of hammering them back-to-back avoids burning the whole quota
# in one sitting and gives you a full day's worth of time-series data.
CALLS_PER_DAY = 333
SECONDS_PER_DAY = 24 * 60 * 60
INTERVAL_SECONDS = SECONDS_PER_DAY // CALLS_PER_DAY  # ~259 seconds (~4.3 min)

# --- Retry behavior ---
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 10  # doubles each retry: 10s, 20s, 40s

# --- MySQL (staging + curated layers) ---
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "crypto_pipeline")

MYSQL_CONN_STRING = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
STAGING_DATA_DIR = PROJECT_ROOT / "data" / "staging"
LOG_DIR = PROJECT_ROOT / "logs"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV_PATH = RAW_DATA_DIR / "crypto_raw.csv"
LOG_FILE_PATH = LOG_DIR / "pipeline.log"
