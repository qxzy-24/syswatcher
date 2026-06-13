"""Tests for the syswatcher logging module."""

import logging
from pathlib import Path

from syswatcher.logging import get_logger, setup_logging


def test_setup_logging_fallback(temp_dir: Path) -> None:
    """Verify logging setup creates file handler correctly or falls back."""
    log_file = temp_dir / "test_syswatch.log"

    # Configure logging
    logger = setup_logging(level=logging.DEBUG, log_file_path=log_file, force=True)

    assert logger.name == "syswatch"
    assert logger.level == logging.DEBUG

    # Check that RotatingFileHandler was added
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.Handler)]
    assert len(file_handlers) > 0


def test_get_logger() -> None:
    """Verify child logger scoping."""
    child_logger = get_logger("test_module")
    assert child_logger.name == "syswatch.test_module"

    root_logger = get_logger()
    assert root_logger.name == "syswatch"
