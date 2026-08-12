"""Struktur logging konfiqurasiyası (structlog)."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", environment: str = "development") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    # Səs-küylü kitabxanaları sakitləşdir.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
