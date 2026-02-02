"""
Logging configuration for FastSurfer surface reconstruction.

Matches fastsurfer_nn logging format for consistency.
"""

import logging
from logging import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    FileHandler,
    Logger,
    StreamHandler,
    basicConfig,
    getLogger,
)
from os import environ
from pathlib import Path
from sys import stdout
from typing import Optional


def setup_logging(log_file_path: Path | str | None = None) -> None:
    """
    Set up logging using fastsurfer_nn format.

    Format: "[%(levelname)s]: %(message)s"
    Log level: From FASTSURFER_LOG_LEVEL env var (default: INFO)

    Parameters
    ----------
    log_file_path : Path or str, optional
        Path to log file. If provided, logs are written to both
        console and file.
    """
    # Set up logging format (matches fastsurfer_nn)
    _FORMAT = "[%(levelname)s]: %(message)s"
    handlers = [StreamHandler(stdout)]

    if log_file_path:
        if not isinstance(log_file_path, Path):
            log_file_path = Path(log_file_path)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(FileHandler(filename=log_file_path, mode="a"))

    # Get log level from environment (matches fastsurfer_nn)
    log_level = environ.get("FASTSURFER_LOG_LEVEL", "INFO").upper()
    if log_level not in ("INFO", "DEBUG", "WARNING", "WARN", "ERROR", "CRITICAL", "FATAL"):
        raise RuntimeError(f"Invalid log level: {log_level}")

    basicConfig(
        level=getattr(logging, log_level),
        format=_FORMAT,
        handlers=handlers,
    )


def get_logger(name: str) -> Logger:
    """
    Get a logger for a module.

    Parameters
    ----------
    name : str
        Module name (typically __name__)

    Returns
    -------
    Logger
        Logger instance
    """
    return getLogger(f"fastsurfer_recon.{name}")

