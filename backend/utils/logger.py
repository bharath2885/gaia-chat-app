"""Centralised logging setup for the Gaia Chat App backend.

Call configure_logging() once at startup (in main.py).
Everywhere else, just use:

    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import logging.handlers
import sys
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / "gaia_chat.log"

CONSOLE_FMT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
FILE_FMT    = "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d) — %(message)s"
DATE_FMT    = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    """Set up console + rotating-file logging.

    Args:
        level: Root log level string, e.g. "DEBUG", "INFO", "WARNING".
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # ── Console handler ───────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(numeric_level)
    console.setFormatter(logging.Formatter(CONSOLE_FMT, datefmt=DATE_FMT))

    # ── Rotating file handler (5 MB × 3 backups) ──────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)   # always capture DEBUG to file
    file_handler.setFormatter(logging.Formatter(FILE_FMT, datefmt=DATE_FMT))

    # ── Root logger ───────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Quieten noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s  file=%s", level.upper(), LOG_FILE
    )
