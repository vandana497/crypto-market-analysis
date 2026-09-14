"""
Centralized configuration for the crypto market cap pipeline.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # reads .env in project root if present

# --- API keys ---
CMC_API_KEY = os.getenv("CMC_API_KEY", "").strip()
CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY", "").strip()
# Note: not hard-raising if CMC_API_KEY is missing - the dashboard imports
# this module too but never calls the CoinMarketCap API, so it shouldn't
# hard-crash on a missing key. fetch.py checks for a valid key itself right
# before making the actual API call, where it's genuinely required.

CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

# --- Request parameters ---
LISTING_START = "1"
LISTING_LIMIT = "50"
CONVERT_CURRENCY = "USD"

# --- Scheduling ---
CALLS_PER_DAY = 333
SECONDS_PER_DAY = 24 * 60 * 60
INTERVAL_SECONDS = SECONDS_PER_DAY // CALLS_PER_DAY  # ~259 seconds (~4.3 min)

# --- Retry behavior ---
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 10

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
