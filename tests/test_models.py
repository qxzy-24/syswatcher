"""Tests for configuration and state models."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest

from syswatcher.models import (
    METRIC_NAMES,
    AlertsConfig,
    AppConfig,
    MetricPolicy,
    MonitorConfig,
    PathsConfig,
    RuntimeState,
    TelegramConfig,
)


def test_metric_names() -> None:
    """Verify supported metric names are present."""
    assert "cpu" in METRIC_NAMES
    assert "ram" in METRIC_NAMES
    assert "disk" in METRIC_NAMES


def test_frozen_models() -> None:
    """Verify that configuration models are frozen (read-only)."""
    policy = MetricPolicy(threshold_percent=90.0, cooldown_minutes=5)
    with pytest.raises(FrozenInstanceError):
        policy.threshold_percent = 95.0  # type: ignore

    paths = PathsConfig(log_file=Path("log.txt"), state_file=Path("state.json"))
    with pytest.raises(FrozenInstanceError):
        paths.log_file = Path("new_log.txt")  # type: ignore


def test_mutable_runtime_state() -> None:
    """Verify that RuntimeState is mutable."""
    state = RuntimeState(last_alert_sent_at={}, active_alerts={"cpu": False})
    state.active_alerts["cpu"] = True
    assert state.active_alerts["cpu"] is True

    now = datetime.now()
    state.last_alert_sent_at["cpu"] = now
    assert state.last_alert_sent_at["cpu"] == now
