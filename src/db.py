"""
MySQL connection handling via SQLAlchemy.

Kept as a single shared engine so we're not opening a fresh connection
per query — same pattern you'd use in a real service.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.settings import MYSQL_CONN_STRING
from src.logger import get_logger

logger = get_logger()

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(MYSQL_CONN_STRING, pool_pre_ping=True)
        logger.info("MySQL engine created.")
    return _engine


def test_connection() -> bool:
    """Quick sanity check you can run after setting up .env — returns True/False."""
    from sqlalchemy import text

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("MySQL connection OK.")
        return True
    except Exception as e:
        logger.error(f"MySQL connection failed: {e}")
        return False
