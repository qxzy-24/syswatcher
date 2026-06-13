"""Entry point and daemon execution loop for syswatch."""

from __future__ import annotations

import argparse
import signal
import time
from pathlib import Path
from typing import Any

from syswatcher.alerting import evaluate_thresholds
from syswatcher.config import load_config
from syswatcher.logging import get_logger, setup_logging
from syswatcher.monitor import get_system_metrics
from syswatcher.notifier import TelegramNotifier
from syswatcher.state import load_runtime_state, save_runtime_state

_possible_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
DEFAULT_CONFIG_PATH = _possible_path if _possible_path.exists() else Path("config.yaml")


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

            state_changed = evaluate_thresholds(
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
        help=f"Path to configuration YAML file (default: {DEFAULT_CONFIG_PATH})",
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
