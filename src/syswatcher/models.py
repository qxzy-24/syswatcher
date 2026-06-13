"""Data models and configuration structures for the syswatch daemon."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

METRIC_NAMES = ("cpu", "ram", "disk")


@dataclass(frozen=True)
class MetricPolicy:
    """Per-metric alert threshold and cooldown settings."""

    threshold_percent: float
    cooldown_minutes: int


@dataclass(frozen=True)
class PathsConfig:
    """Filesystem paths used by the daemon."""

    log_file: Path
    state_file: Path


@dataclass(frozen=True)
class MonitorConfig:
    """Metric collection settings."""

    disk_mountpoint: str | None
    top_process_count: int


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram integration and retry settings."""

    bot_token: str
    chat_id: str
    request_timeout_seconds: int
    retry_max_attempts: int
    retry_initial_delay_seconds: float
    retry_backoff_factor: float


@dataclass(frozen=True)
class AlertsConfig:
    """Alert policy for each monitored metric."""

    cpu: MetricPolicy
    ram: MetricPolicy
    disk: MetricPolicy


@dataclass
class RuntimeState:
    """Persistent alert runtime state stored on disk."""

    last_alert_sent_at: Dict[str, datetime]
    active_alerts: Dict[str, bool]


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration loaded from config.yaml."""

    check_interval_seconds: int
    paths: PathsConfig
    monitor: MonitorConfig
    telegram: TelegramConfig
    alerts: AlertsConfig
