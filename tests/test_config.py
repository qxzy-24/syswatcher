"""Tests for configuration parsing, validation, and overrides."""

import os
from pathlib import Path
from unittest import mock

import pytest
import yaml

from syswatcher.config import load_config


def test_load_valid_config(mock_config_yaml: Path) -> None:
    """Verify loading a valid configuration yaml file."""
    config = load_config(mock_config_yaml)

    assert config.check_interval_seconds == 15
    assert config.monitor.top_process_count == 3
    assert config.telegram.bot_token == "123456789:TEST_BOT_TOKEN"
    assert config.telegram.chat_id == "123456789"
    assert config.alerts.cpu.threshold_percent == 90.0
    assert config.alerts.cpu.cooldown_minutes == 5


def test_load_config_missing_file() -> None:
    """Verify load_config raises ValueError when file does not exist."""
    non_existent = Path("non_existent_file.yaml")
    with pytest.raises(ValueError, match="Configuration file not found"):
        load_config(non_existent)


def test_load_config_invalid_type(temp_dir: Path) -> None:
    """Verify top-level type validation."""
    config_file = temp_dir / "invalid.yaml"
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump([1, 2, 3], f)  # List instead of dict

    with pytest.raises(ValueError, match="Top-level YAML structure must be a mapping"):
        load_config(config_file)


def test_load_config_missing_telegram_secrets(temp_dir: Path) -> None:
    """Verify bot token and chat id are required."""
    config_data = {
        "paths": {},
        "telegram": {},
    }
    config_file = temp_dir / "missing_secrets.yaml"
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)

    with pytest.raises(ValueError, match="Missing Telegram bot token"):
        load_config(config_file)


def test_load_config_env_overrides(mock_config_yaml: Path) -> None:
    """Verify that environment variables take precedence over config.yaml."""
    env_vars = {
        "SYSWATCH_BOT_TOKEN": "env_bot_token",
        "SYSWATCH_CHAT_ID": "env_chat_id",
    }
    with mock.patch.dict(os.environ, env_vars):
        config = load_config(mock_config_yaml)
        assert config.telegram.bot_token == "env_bot_token"
        assert config.telegram.chat_id == "env_chat_id"


def test_load_config_dotenv_file(temp_dir: Path) -> None:
    """Verify that configuration loads secrets from a local .env file."""
    config_data = {
        "paths": {},
        "telegram": {
            "bot_token": "placeholder_bot_token",
            "chat_id": "placeholder_chat_id",
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

    # Write a local .env file in the config directory
    dotenv_file = temp_dir / ".env"
    with dotenv_file.open("w", encoding="utf-8") as f:
        f.write("SYSWATCH_BOT_TOKEN=dotenv_token\n")
        f.write("SYSWATCH_CHAT_ID=dotenv_chat_id\n")

    # Clear environment variables if they are set in parent environment
    with mock.patch.dict(os.environ, {}, clear=True):
        config = load_config(config_file)
        assert config.telegram.bot_token == "dotenv_token"
        assert config.telegram.chat_id == "dotenv_chat_id"
