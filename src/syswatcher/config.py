"""Configuration parsing and validation module for syswatch.

This module supports reading YAML configurations and overriding secrets (like
Telegram bot token and chat ID) from environment variables or a .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

from syswatcher.models import (
    AlertsConfig,
    AppConfig,
    MetricPolicy,
    MonitorConfig,
    PathsConfig,
    TelegramConfig,
)


def _resolve_path(path_value: str, base_dir: Path) -> Path:
    """Resolve a path value relative to the config file location."""
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate

    return (base_dir / candidate).resolve()


def _require_key(data: Dict[str, Any], key: str) -> Any:
    """Return a required key from a dictionary or raise a ValueError."""
    if key not in data:
        raise ValueError(f"Missing required config key: {key}")

    return data[key]


def _to_float(value: Any, key_name: str, minimum: float | None = None) -> float:
    """Convert a value to float with a clear config validation error."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key '{key_name}' must be a number.") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(f"Config key '{key_name}' must be >= {minimum}.")

    return parsed


def _to_int(value: Any, key_name: str, minimum: int) -> int:
    """Convert a value to int and enforce a minimum bound."""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key '{key_name}' must be an integer.") from exc

    if parsed < minimum:
        raise ValueError(f"Config key '{key_name}' must be >= {minimum}.")

    return parsed


def _load_metric_policy(
    metric_name: str,
    alerts_raw: Dict[str, Any],
    legacy_thresholds: Dict[str, Any],
    legacy_cooldown_minutes: Any,
) -> MetricPolicy:
    """Load a per-metric policy from modern config or legacy fallback keys."""
    if metric_name in alerts_raw:
        metric_raw = alerts_raw[metric_name]
        if not isinstance(metric_raw, dict):
            raise ValueError(f"Config key 'alerts.{metric_name}' must be a mapping/object.")

        return MetricPolicy(
            threshold_percent=_to_float(
                _require_key(metric_raw, "threshold_percent"),
                f"alerts.{metric_name}.threshold_percent",
            ),
            cooldown_minutes=_to_int(
                _require_key(metric_raw, "cooldown_minutes"),
                f"alerts.{metric_name}.cooldown_minutes",
                minimum=0,
            ),
        )

    legacy_metric_key = f"{metric_name}_percent"
    return MetricPolicy(
        threshold_percent=_to_float(
            _require_key(legacy_thresholds, legacy_metric_key),
            f"thresholds.{legacy_metric_key}",
        ),
        cooldown_minutes=_to_int(legacy_cooldown_minutes, "cooldown_minutes", minimum=0),
    )


def load_config(config_path: Path) -> AppConfig:
    """Load and validate daemon configuration from YAML, merging environment variables."""
    # Load environment variables from .env if present.
    load_dotenv()  # Searches current working directory
    if config_path:
        env_file = config_path.parent / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file)

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            raw = yaml.safe_load(config_file) or {}
    except FileNotFoundError as exc:
        raise ValueError(f"Configuration file not found: {config_path}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Top-level YAML structure must be a mapping/object.")

    config_base_dir = config_path.resolve().parent

    paths_raw = raw.get("paths", {})
    if not isinstance(paths_raw, dict):
        raise ValueError("Config key 'paths' must be a mapping/object.")

    paths = PathsConfig(
        log_file=_resolve_path(str(paths_raw.get("log_file", "./logs/syswatch.log")), config_base_dir),
        state_file=_resolve_path(str(paths_raw.get("state_file", "./state/state.json")), config_base_dir),
    )

    monitor_raw = raw.get("monitor", {})
    if not isinstance(monitor_raw, dict):
        raise ValueError("Config key 'monitor' must be a mapping/object.")

    disk_mountpoint_raw = monitor_raw.get("disk_mountpoint", "auto")
    disk_mountpoint = None
    if disk_mountpoint_raw is not None:
        disk_mountpoint_text = str(disk_mountpoint_raw).strip()
        if disk_mountpoint_text and disk_mountpoint_text.lower() != "auto":
            disk_mountpoint = disk_mountpoint_text

    monitor = MonitorConfig(
        disk_mountpoint=disk_mountpoint,
        top_process_count=_to_int(monitor_raw.get("top_process_count", 3), "monitor.top_process_count", minimum=1),
    )

    telegram_raw = raw.get("telegram", {})
    if not isinstance(telegram_raw, dict):
        raise ValueError("Config key 'telegram' must be a mapping/object.")

    # Prioritize environment variables (.env / OS environment) for Telegram secrets.
    bot_token = (
        os.environ.get("SYSWATCH_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or telegram_raw.get("bot_token", raw.get("telegram_bot_token"))
    )
    chat_id = (
        os.environ.get("SYSWATCH_CHAT_ID")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or telegram_raw.get("chat_id", raw.get("telegram_chat_id"))
    )

    if not bot_token:
        raise ValueError("Missing Telegram bot token. Set telegram.bot_token or SYSWATCH_BOT_TOKEN.")
    if not chat_id:
        raise ValueError("Missing Telegram chat ID. Set telegram.chat_id or SYSWATCH_CHAT_ID.")

    telegram = TelegramConfig(
        bot_token=str(bot_token),
        chat_id=str(chat_id),
        request_timeout_seconds=_to_int(
            telegram_raw.get("request_timeout_seconds", 10),
            "telegram.request_timeout_seconds",
            minimum=1,
        ),
        retry_max_attempts=_to_int(
            telegram_raw.get("retry_max_attempts", 4),
            "telegram.retry_max_attempts",
            minimum=1,
        ),
        retry_initial_delay_seconds=_to_float(
            telegram_raw.get("retry_initial_delay_seconds", 2.0),
            "telegram.retry_initial_delay_seconds",
            minimum=0.1,
        ),
        retry_backoff_factor=_to_float(
            telegram_raw.get("retry_backoff_factor", 2.0),
            "telegram.retry_backoff_factor",
            minimum=1.0,
        ),
    )

    alerts_raw = raw.get("alerts", {})
    if not isinstance(alerts_raw, dict):
        raise ValueError("Config key 'alerts' must be a mapping/object.")

    legacy_thresholds = raw.get("thresholds", {})
    if not isinstance(legacy_thresholds, dict):
        raise ValueError("Config key 'thresholds' must be a mapping/object.")

    alerts = AlertsConfig(
        cpu=_load_metric_policy("cpu", alerts_raw, legacy_thresholds, raw.get("cooldown_minutes", 10)),
        ram=_load_metric_policy("ram", alerts_raw, legacy_thresholds, raw.get("cooldown_minutes", 10)),
        disk=_load_metric_policy("disk", alerts_raw, legacy_thresholds, raw.get("cooldown_minutes", 10)),
    )

    return AppConfig(
        check_interval_seconds=_to_int(raw.get("check_interval_seconds", 15), "check_interval_seconds", minimum=1),
        paths=paths,
        monitor=monitor,
        telegram=telegram,
        alerts=alerts,
    )
