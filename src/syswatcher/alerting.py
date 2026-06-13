"""Threshold evaluation and alerting logic for the syswatch daemon."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from syswatcher.logging import get_logger
from syswatcher.models import AlertsConfig, AppConfig, MetricPolicy, RuntimeState
from syswatcher.notifier import TelegramNotifier
from syswatcher.state import cooldown_remaining


def _metric_policy_map(alerts: AlertsConfig) -> Dict[str, MetricPolicy]:
    """Return alert policies in a dictionary keyed by metric name."""
    return {
        "cpu": alerts.cpu,
        "ram": alerts.ram,
        "disk": alerts.disk,
    }


def evaluate_thresholds(
    metrics: Dict[str, Any],
    config: AppConfig,
    notifier: TelegramNotifier,
    state: RuntimeState,
) -> bool:
    """Evaluate thresholds and send high/recovery alerts.

    Returns:
        bool: True when runtime state changed and should be persisted to disk.
    """
    logger = get_logger(__name__)
    state_changed = False
    now_utc = datetime.now(timezone.utc)

    metric_values = {
        "cpu": float(metrics.get("cpu_percent", 0.0)),
        "ram": float(metrics.get("ram_percent", 0.0)),
        "disk": float(metrics.get("disk_percent", 0.0)),
    }
    top_processes = metrics.get("top_processes", {})

    for metric_name, policy in _metric_policy_map(config.alerts).items():
        current_value = metric_values[metric_name]
        threshold = policy.threshold_percent

        if current_value >= threshold:
            cooldown_window = timedelta(minutes=policy.cooldown_minutes)
            remaining = cooldown_remaining(metric_name, now_utc, state, cooldown_window)

            if remaining.total_seconds() > 0:
                logger.warning(
                    "Suppressed %s alert during cooldown. current=%.2f%% threshold=%.2f%% remaining=%ds",
                    metric_name,
                    current_value,
                    threshold,
                    int(remaining.total_seconds()),
                )
                continue

            culprit_processes = None
            if metric_name in {"cpu", "ram"} and isinstance(top_processes, dict):
                raw_processes = top_processes.get(metric_name, [])
                if isinstance(raw_processes, list):
                    culprit_processes = raw_processes

            alert_sent = notifier.send_threshold_alert(
                metric_name=metric_name,
                current_value=current_value,
                threshold_value=threshold,
                culprit_processes=culprit_processes,
            )

            if alert_sent:
                state.last_alert_sent_at[metric_name] = now_utc
                state.active_alerts[metric_name] = True
                state_changed = True
                logger.warning(
                    "%s exceeded threshold and alert was sent. current=%.2f%% threshold=%.2f%%",
                    metric_name,
                    current_value,
                    threshold,
                )
            else:
                logger.error(
                    "%s exceeded threshold but Telegram alert failed. current=%.2f%% threshold=%.2f%%",
                    metric_name,
                    current_value,
                    threshold,
                )

            continue

        if state.active_alerts.get(metric_name, False):
            recovered = notifier.send_recovery_alert(
                metric_name=metric_name,
                current_value=current_value,
                threshold_value=threshold,
            )

            if recovered:
                state.active_alerts[metric_name] = False
                state_changed = True
                logger.info(
                    "%s recovered and recovery alert was sent. current=%.2f%% threshold=%.2f%%",
                    metric_name,
                    current_value,
                    threshold,
                )
            else:
                logger.error(
                    "%s recovered but recovery notification failed. current=%.2f%% threshold=%.2f%%",
                    metric_name,
                    current_value,
                    threshold,
                )

    return state_changed
