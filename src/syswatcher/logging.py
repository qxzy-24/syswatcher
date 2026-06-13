"""Central logging setup for the syswatch daemon.

This module exposes helper functions for creating and reconfiguring the shared
syswatch logger. Logging uses file rotation to prevent uncontrolled growth in
24/7 deployments.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Safe default when a config file does not provide a custom location.
DEFAULT_LOG_FILE = Path("./logs/syswatch.log")

# Log format required by the project specification.
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(module)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotate at 5 MB and keep 3 backup files.
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


def _resolve_log_file_path(log_file_path: str | Path | None) -> Path:
    """Resolve a configured log file path into an absolute path."""
    configured_path = Path(log_file_path).expanduser() if log_file_path else DEFAULT_LOG_FILE

    if configured_path.is_absolute():
        return configured_path

    # Resolve relative paths from the process working directory.
    return (Path.cwd() / configured_path).resolve()


def _clear_handlers(logger: logging.Logger) -> None:
    """Detach and close all logger handlers to support safe reconfiguration."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # pylint: disable=broad-except
            # Closing errors should never stop the daemon.
            pass


def setup_logging(
    level: int = logging.INFO,
    log_file_path: str | Path | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure and return the shared syswatch logger.

    Args:
        level: Logging threshold.
        log_file_path: Optional custom destination for the rotating log file.
        force: If True, always rebuild handlers even when already configured.

    The setup is idempotent for unchanged configuration and safely supports
    reconfiguration when a new log file path is provided.
    """
    logger = logging.getLogger("syswatch")
    logger.setLevel(level)
    logger.propagate = False

    resolved_log_file = _resolve_log_file_path(log_file_path)
    current_log_file = getattr(logger, "_syswatch_log_file", None)

    if logger.handlers and not force and current_log_file == str(resolved_log_file):
        return logger

    if logger.handlers:
        _clear_handlers(logger)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    try:
        # Ensure log directory exists before creating the rotating file handler.
        resolved_log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=str(resolved_log_file),
            maxBytes=MAX_LOG_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        setattr(logger, "_syswatch_log_file", str(resolved_log_file))
    except Exception as exc:  # pylint: disable=broad-except
        # If file logging cannot be initialized (permissions/path issues),
        # keep the daemon observable by falling back to stderr.
        fallback_handler = logging.StreamHandler(sys.stderr)
        fallback_handler.setFormatter(formatter)
        logger.addHandler(fallback_handler)
        setattr(logger, "_syswatch_log_file", None)
        logger.error("Failed to initialize file logging at %s: %s", resolved_log_file, exc)

    return logger


def get_logger(module_name: str | None = None) -> logging.Logger:
    """Return a child logger scoped to the given module name."""
    base_logger = logging.getLogger("syswatch")
    if not base_logger.handlers:
        base_logger = setup_logging()

    if module_name:
        return base_logger.getChild(module_name)

    return base_logger
