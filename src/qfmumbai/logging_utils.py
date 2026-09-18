"""Console + file logging. Every script logs the config hash for provenance."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import ROOT

_FMT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def get_logger(name: str, cfg=None) -> logging.Logger:
    level = (cfg.get_in("logging.level", "INFO") if cfg else "INFO").upper()
    logfile = ROOT / (cfg.get_in("logging.file", "logs/run.log") if cfg else "logs/run.log")
    logfile.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(_FMT, datefmt="%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if cfg is not None:
        logger.info("config=%s hash=%s", getattr(cfg, "_path", "?"), cfg.hash)
    return logger
