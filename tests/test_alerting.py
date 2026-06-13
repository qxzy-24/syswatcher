"""Tests for threshold evaluation and alerting logic."""

from datetime import datetime, timezone
from unittest import mock

from syswatcher.alerting import evaluate_thresholds
from syswatcher.config import AppConfig
from syswatcher.models import AlertsConfig, AppConfig, MetricPolicy, PathsConfig, RuntimeState
from syswatcher.notifier import TelegramNotifier


def test_evaluate_thresholds_no_alerts() -> None:
    """Verify that under-threshold metrics do not trigger alerts."""
    # Config
    alerts = AlertsConfig(
        cpu=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        ram=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        disk=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
    )
    config = AppConfig(
        check_interval_seconds=15,
        paths=PathsConfig(log_file=mock.Mock(), state_file=mock.Mock()),
        monitor=mock.Mock(),
        telegram=mock.Mock(),
        alerts=alerts,
    )

    # State & Notifier
    state = RuntimeState(last_alert_sent_at={}, active_alerts={"cpu": False, "ram": False, "disk": False})
    notifier = mock.create_autospec(TelegramNotifier)

    metrics = {
        "cpu_percent": 50.0,
        "ram_percent": 60.0,
        "disk_percent": 70.0,
    }

    state_changed = evaluate_thresholds(metrics, config, notifier, state)

    assert state_changed is False
    assert notifier.send_threshold_alert.called is False
    assert notifier.send_recovery_alert.called is False


def test_evaluate_thresholds_trigger_alert() -> None:
    """Verify that crossing threshold triggers alert and updates state."""
    alerts = AlertsConfig(
        cpu=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        ram=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        disk=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
    )
    config = AppConfig(
        check_interval_seconds=15,
        paths=PathsConfig(log_file=mock.Mock(), state_file=mock.Mock()),
        monitor=mock.Mock(),
        telegram=mock.Mock(),
        alerts=alerts,
    )

    state = RuntimeState(last_alert_sent_at={}, active_alerts={"cpu": False, "ram": False, "disk": False})
    notifier = mock.create_autospec(TelegramNotifier)
    notifier.send_threshold_alert.return_value = True

    metrics = {
        "cpu_percent": 95.0,
        "ram_percent": 60.0,
        "disk_percent": 70.0,
        "top_processes": {"cpu": [{"pid": 1, "name": "bad_process", "cpu_percent": 90.0}]},
    }

    state_changed = evaluate_thresholds(metrics, config, notifier, state)

    assert state_changed is True
    assert state.active_alerts["cpu"] is True
    assert "cpu" in state.last_alert_sent_at
    notifier.send_threshold_alert.assert_called_once_with(
        metric_name="cpu",
        current_value=95.0,
        threshold_value=90.0,
        culprit_processes=[{"pid": 1, "name": "bad_process", "cpu_percent": 90.0}],
    )


def test_evaluate_thresholds_cooldown_suppression() -> None:
    """Verify that cooldown mutes alerts inside the window."""
    alerts = AlertsConfig(
        cpu=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        ram=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        disk=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
    )
    config = AppConfig(
        check_interval_seconds=15,
        paths=PathsConfig(log_file=mock.Mock(), state_file=mock.Mock()),
        monitor=mock.Mock(),
        telegram=mock.Mock(),
        alerts=alerts,
    )

    # Set last alert to just now
    now = datetime.now(timezone.utc)
    state = RuntimeState(
        last_alert_sent_at={"cpu": now},
        active_alerts={"cpu": True, "ram": False, "disk": False},
    )
    notifier = mock.create_autospec(TelegramNotifier)

    metrics = {
        "cpu_percent": 98.0,
        "ram_percent": 60.0,
        "disk_percent": 70.0,
    }

    state_changed = evaluate_thresholds(metrics, config, notifier, state)

    # Alert should be suppressed, state unchanged
    assert state_changed is False
    assert notifier.send_threshold_alert.called is False


def test_evaluate_thresholds_recovery() -> None:
    """Verify recovery alert triggers when active alert drops below threshold."""
    alerts = AlertsConfig(
        cpu=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        ram=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
        disk=MetricPolicy(threshold_percent=90.0, cooldown_minutes=5),
    )
    config = AppConfig(
        check_interval_seconds=15,
        paths=PathsConfig(log_file=mock.Mock(), state_file=mock.Mock()),
        monitor=mock.Mock(),
        telegram=mock.Mock(),
        alerts=alerts,
    )

    state = RuntimeState(last_alert_sent_at={}, active_alerts={"cpu": True, "ram": False, "disk": False})
    notifier = mock.create_autospec(TelegramNotifier)
    notifier.send_recovery_alert.return_value = True

    metrics = {
        "cpu_percent": 50.0,
        "ram_percent": 60.0,
        "disk_percent": 70.0,
    }

    state_changed = evaluate_thresholds(metrics, config, notifier, state)

    assert state_changed is True
    assert state.active_alerts["cpu"] is False
    notifier.send_recovery_alert.assert_called_once_with(
        metric_name="cpu",
        current_value=50.0,
        threshold_value=90.0,
    )
