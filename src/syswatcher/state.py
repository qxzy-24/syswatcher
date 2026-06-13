"""State management and persistence for the syswatch daemon."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from syswatcher.logging import get_logger
from syswatcher.models import METRIC_NAMES, RuntimeState


def default_runtime_state() -> RuntimeState:
    """Create an empty runtime state object."""
    return RuntimeState(last_alert_sent_at={}, active_alerts={name: False for name in METRIC_NAMES})


def _parse_utc_timestamp(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    normalized = value.strip().replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _to_utc_iso(timestamp: datetime) -> str:
    """Convert a datetime into a UTC ISO-8601 string for JSON storage."""
    return timestamp.astimezone(timezone.utc).isoformat()


def load_runtime_state(state_file: Path) -> RuntimeState:
    """Load alert state from disk so cooldown survives process restarts."""
    logger = get_logger(__name__)
    state = default_runtime_state()

    if not state_file.exists():
        return state

    try:
        with state_file.open("r", encoding="utf-8") as state_handle:
            payload = json.load(state_handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Unable to read runtime state file %s: %s", state_file, exc)
        return state

    if not isinstance(payload, dict):
        logger.error("Runtime state file %s is not a JSON object.", state_file)
        return state

    last_alerts_raw = payload.get("last_alert_sent_at", {})
    if isinstance(last_alerts_raw, dict):
        for metric_name in METRIC_NAMES:
            raw_timestamp = last_alerts_raw.get(metric_name)
            if not isinstance(raw_timestamp, str):
                continue

            parsed = _parse_utc_timestamp(raw_timestamp)
            if parsed is None:
                logger.warning(
                    "Ignoring invalid timestamp for metric '%s' in state file: %s",
                    metric_name,
                    raw_timestamp,
                )
                continue

            state.last_alert_sent_at[metric_name] = parsed

    active_alerts_raw = payload.get("active_alerts", {})
    if isinstance(active_alerts_raw, dict):
        for metric_name in METRIC_NAMES:
            state.active_alerts[metric_name] = bool(active_alerts_raw.get(metric_name, False))

    return state


def save_runtime_state(state_file: Path, state: RuntimeState) -> None:
    """Persist runtime state atomically to avoid partial writes on crashes."""
    logger = get_logger(__name__)

    payload = {
        "version": 1,
        "last_alert_sent_at": {
            metric_name: _to_utc_iso(timestamp)
            for metric_name, timestamp in state.last_alert_sent_at.items()
            if metric_name in METRIC_NAMES
        },
        "active_alerts": {
            metric_name: bool(state.active_alerts.get(metric_name, False))
            for metric_name in METRIC_NAMES
        },
    }

    temp_state_file = state_file.with_suffix(f"{state_file.suffix}.tmp")

    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        with temp_state_file.open("w", encoding="utf-8") as state_handle:
            json.dump(payload, state_handle, indent=2, sort_keys=True)
        temp_state_file.replace(state_file)
    except OSError as exc:
        logger.error("Failed to persist runtime state to %s: %s", state_file, exc)


def cooldown_remaining(
    metric_name: str,
    now_utc: datetime,
    state: RuntimeState,
    cooldown_window: timedelta,
) -> timedelta:
    """Return remaining cooldown for a metric, or zero when alerting is allowed."""
    if cooldown_window.total_seconds() <= 0:
        return timedelta(0)

    last_sent = state.last_alert_sent_at.get(metric_name)
    if last_sent is None:
        return timedelta(0)

    elapsed = now_utc - last_sent
    if elapsed >= cooldown_window:
        return timedelta(0)

    return cooldown_window - elapsed
