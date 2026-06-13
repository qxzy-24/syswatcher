"""Tests for state serialization, deserialization, and cooldown logic."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from syswatcher.models import RuntimeState
from syswatcher.state import (
    _parse_utc_timestamp,
    _to_utc_iso,
    cooldown_remaining,
    default_runtime_state,
    load_runtime_state,
    save_runtime_state,
)


def test_default_runtime_state() -> None:
    """Verify initialization of default runtime state."""
    state = default_runtime_state()
    assert state.last_alert_sent_at == {}
    assert state.active_alerts == {"cpu": False, "ram": False, "disk": False}


def test_timestamp_serialization() -> None:
    """Verify ISO timestamp conversions."""
    dt = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
    iso_str = _to_utc_iso(dt)
    assert iso_str == "2026-06-08T12:00:00+00:00"

    parsed = _parse_utc_timestamp(iso_str)
    assert parsed == dt


def test_state_roundtrip(temp_dir: Path) -> None:
    """Verify loading and saving state to a file."""
    state_file = temp_dir / "state.json"
    state = default_runtime_state()

    dt = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
    state.last_alert_sent_at["cpu"] = dt
    state.active_alerts["cpu"] = True

    # Save
    save_runtime_state(state_file, state)
    assert state_file.exists()

    # Load
    loaded_state = load_runtime_state(state_file)
    assert loaded_state.active_alerts["cpu"] is True
    assert loaded_state.last_alert_sent_at["cpu"] == dt
    assert loaded_state.active_alerts["ram"] is False


def test_cooldown_calculations() -> None:
    """Verify cooldown remaining logic."""
    state = RuntimeState(last_alert_sent_at={}, active_alerts={})
    now = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
    cooldown = timedelta(minutes=5)

    # Case 1: No previous alert
    assert cooldown_remaining("cpu", now, state, cooldown) == timedelta(0)

    # Case 2: Cooldown expired
    state.last_alert_sent_at["cpu"] = now - timedelta(minutes=6)
    assert cooldown_remaining("cpu", now, state, cooldown) == timedelta(0)

    # Case 3: Inside cooldown window
    state.last_alert_sent_at["cpu"] = now - timedelta(minutes=2)
    remaining = cooldown_remaining("cpu", now, state, cooldown)
    assert remaining == timedelta(minutes=3)
