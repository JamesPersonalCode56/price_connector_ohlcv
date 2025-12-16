from __future__ import annotations

import logging
import os
from typing import Final

LOG_LEVEL_ENV_VAR: Final = "CONNECTOR_LOG_LEVEL"
LOG_FORMAT: Final = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"


class ColorFormatter(logging.Formatter):
    COLORS: Final = {
        logging.DEBUG: "\033[37m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[41m",
    }
    RESET: Final = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        formatted = super().format(record)
        return f"{color}{formatted}{self.RESET}"


def _resolve_level() -> int:
    raw_level = os.getenv(LOG_LEVEL_ENV_VAR, "INFO").strip().upper()
    return getattr(logging, raw_level, logging.INFO)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if any(
        isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers
    ):
        return

    level = _resolve_level()
    root_logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(ColorFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(handler)
