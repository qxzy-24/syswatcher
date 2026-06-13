"""Shared fixtures for syswatcher tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pytest
import yaml


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory Path."""
    return tmp_path


@pytest.fixture
def mock_config_yaml(temp_dir: Path) -> Generator[Path, None, None]:
    """Fixture to create a temporary config.yaml file."""
    config_data = {
        "paths": {
            "log_file": str(temp_dir / "logs" / "syswatch.log"),
            "state_file": str(temp_dir / "state" / "state.json"),
        },
        "check_interval_seconds": 15,
        "monitor": {
            "disk_mountpoint": "auto",
            "top_process_count": 3,
        },
        "telegram": {
            "bot_token": "123456789:TEST_BOT_TOKEN",
            "chat_id": "123456789",
            "request_timeout_seconds": 10,
            "retry_max_attempts": 3,
            "retry_initial_delay_seconds": 0.1,
            "retry_backoff_factor": 1.5,
        },
        "alerts": {
            "cpu": {"threshold_percent": 90.0, "cooldown_minutes": 5},
            "ram": {"threshold_percent": 85.0, "cooldown_minutes": 10},
            "disk": {"threshold_percent": 80.0, "cooldown_minutes": 30},
        },
    }

    config_file = temp_dir / "config.yaml"
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)

    yield config_file
