"""
Logging setup shared across the pipeline.

Why: a plain print() (like the original notebook) gives you nothing once
the loop is running unattended for hours. A real log file lets you answer
"did last night's runs succeed?" without re-running anything, and is the
foundation for the pipeline health / observability tab in the dashboard.
"""

import logging
from config.settings import LOG_FILE_PATH


def get_logger(name: str = "crypto_pipeline") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        # avoid duplicate handlers if get_logger() is called more than once
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE_PATH)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
