"""Entry point for the syswatch monitoring daemon.

The daemon runs continuously, collects host metrics, evaluates thresholds,
and sends Telegram alerts with per-metric cooldown control.
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from logger import get_logger, setup_logging
from monitor import get_system_metrics
from notifier import TelegramNotifier

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
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


def _default_runtime_state() -> RuntimeState:
    """Create an empty runtime state object."""
    return RuntimeState(last_alert_sent_at={}, active_alerts={name: False for name in METRIC_NAMES})


def _metric_policy_map(alerts: AlertsConfig) -> Dict[str, MetricPolicy]:
    """Return alert policies in a dictionary keyed by metric name."""
    return {
        "cpu": alerts.cpu,
        "ram": alerts.ram,
        "disk": alerts.disk,
    }


def _resolve_path(path_value: str, base_dir: Path) -> Path:
    """Resolve a path value relative to the config file location."""
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate

    return (base_dir / candidate).resolve()


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
    """Load and validate daemon configuration from YAML."""
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

    bot_token = telegram_raw.get("bot_token", raw.get("telegram_bot_token"))
    chat_id = telegram_raw.get("chat_id", raw.get("telegram_chat_id"))

    if not bot_token:
        raise ValueError("Missing Telegram bot token. Set telegram.bot_token in config.yaml.")
    if not chat_id:
        raise ValueError("Missing Telegram chat ID. Set telegram.chat_id in config.yaml.")

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


def load_runtime_state(state_file: Path) -> RuntimeState:
    """Load alert state from disk so cooldown survives process restarts."""
    logger = get_logger(__name__)
    state = _default_runtime_state()

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


def _cooldown_remaining(
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


def _evaluate_thresholds(
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
            remaining = _cooldown_remaining(metric_name, now_utc, state, cooldown_window)

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


def run_daemon(config_path: Path) -> None:
    """Run syswatch forever with robust exception handling."""
    # Load configuration first, then configure logging to the configured target.
    config = load_config(config_path)
    setup_logging(log_file_path=config.paths.log_file, force=True)
    logger = get_logger(__name__)

    notifier = TelegramNotifier(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        timeout_seconds=config.telegram.request_timeout_seconds,
        retry_max_attempts=config.telegram.retry_max_attempts,
        retry_initial_delay_seconds=config.telegram.retry_initial_delay_seconds,
        retry_backoff_factor=config.telegram.retry_backoff_factor,
    )

    state = load_runtime_state(config.paths.state_file)

    logger.info(
        "Syswatch started. interval=%ss disk_target=%s log_file=%s state_file=%s",
        config.check_interval_seconds,
        config.monitor.disk_mountpoint or "auto",
        config.paths.log_file,
        config.paths.state_file,
    )
    logger.info(
        "Alert policies: cpu(threshold=%.2f cooldown=%sm) ram(threshold=%.2f cooldown=%sm) disk(threshold=%.2f cooldown=%sm)",
        config.alerts.cpu.threshold_percent,
        config.alerts.cpu.cooldown_minutes,
        config.alerts.ram.threshold_percent,
        config.alerts.ram.cooldown_minutes,
        config.alerts.disk.threshold_percent,
        config.alerts.disk.cooldown_minutes,
    )

    # Graceful shutdown on SIGTERM / SIGINT.
    shutdown_requested = False

    def _handle_shutdown(signum: int, _frame: Any) -> None:
        nonlocal shutdown_requested
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — initiating graceful shutdown.", sig_name)
        shutdown_requested = True

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    while not shutdown_requested:
        cycle_start = time.monotonic()

        try:
            metrics = get_system_metrics(
                disk_mountpoint=config.monitor.disk_mountpoint,
                top_process_count=config.monitor.top_process_count,
            )
            logger.debug("Metrics snapshot: %s", metrics)

            state_changed = _evaluate_thresholds(
                metrics=metrics,
                config=config,
                notifier=notifier,
                state=state,
            )

            if state_changed:
                save_runtime_state(config.paths.state_file, state)
        except Exception:  # pylint: disable=broad-except
            # Never allow a single unexpected failure to kill the daemon loop.
            logger.critical("Unhandled exception in monitoring loop.", exc_info=True)
        finally:
            elapsed = time.monotonic() - cycle_start
            sleep_seconds = max(config.check_interval_seconds - elapsed, 0.0)
            # Break sleep into short segments so signals are handled promptly.
            sleep_end = time.monotonic() + sleep_seconds
            while time.monotonic() < sleep_end and not shutdown_requested:
                time.sleep(min(sleep_end - time.monotonic(), 1.0))

    # Persist final state before exit.
    save_runtime_state(config.paths.state_file, state)
    logger.info("Syswatch stopped gracefully.")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for daemon startup."""
    parser = argparse.ArgumentParser(description="Syswatch 24/7 system monitoring daemon")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to configuration YAML file (default: ./config.yaml)",
    )
    return parser.parse_args()


def main() -> None:
    """Top-level startup wrapper for service-friendly failure logging."""
    # Bootstrap logging early so startup failures are always visible.
    setup_logging(force=True)
    logger = get_logger(__name__)

    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    try:
        run_daemon(config_path=config_path)
    except Exception:  # pylint: disable=broad-except
        logger.critical("Fatal startup error in syswatch.", exc_info=True)
        raise


if __name__ == "__main__":
    main()
