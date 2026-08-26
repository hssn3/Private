"""Rotating log file inside 0\\Data plus a console mirror."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import paths

_CONFIGURED = False


def setup() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("backupsuite")
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        handler = RotatingFileHandler(
            paths.log_file(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    except OSError:
        pass  # read-only location - console logging still works

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    _CONFIGURED = True
    return logger


log = setup()
