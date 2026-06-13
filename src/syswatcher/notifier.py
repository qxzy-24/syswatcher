"""Telegram notification utilities for syswatch.

All Telegram network interactions are wrapped in robust error handling so
transient failures never crash the monitoring daemon.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import requests

from syswatcher.logging import get_logger

_LOGGER: "logging.Logger | None" = None


def _get_module_logger() -> "logging.Logger":
    """Return the module logger, creating it lazily to avoid premature setup."""
    global _LOGGER  # noqa: PLW0603
    if _LOGGER is None:
        _LOGGER = get_logger(__name__)
    return _LOGGER


class TelegramNotifier:
    """Send alert messages to a Telegram chat using the Bot API."""

    BASE_URL = "https://api.telegram.org"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: int = 10,
        retry_max_attempts: int = 4,
        retry_initial_delay_seconds: float = 2.0,
        retry_backoff_factor: float = 2.0,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.timeout_seconds = timeout_seconds
        self.retry_max_attempts = max(1, int(retry_max_attempts))
        self.retry_initial_delay_seconds = max(0.1, float(retry_initial_delay_seconds))
        self.retry_backoff_factor = max(1.0, float(retry_backoff_factor))
        self.endpoint = f"{self.BASE_URL}/bot{self.bot_token}/sendMessage"

    def send_message(self, message: str) -> bool:
        """Send a raw text message to Telegram.

        Returns:
            bool: True if Telegram accepts the message, otherwise False.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "link_preview_options": {"is_disabled": True},
        }

        retry_delay = self.retry_initial_delay_seconds

        for attempt in range(1, self.retry_max_attempts + 1):
            retry_reason = "unknown error"

            try:
                response = requests.post(self.endpoint, json=payload, timeout=self.timeout_seconds)

                if response.status_code == 429:
                    try:
                        result = response.json()
                        retry_after = result.get("parameters", {}).get("retry_after")
                        if retry_after:
                            retry_delay = float(retry_after)
                    except ValueError:
                        pass
                    retry_reason = f"rate-limited by Telegram: {response.text[:200]}"
                    raise RuntimeError(retry_reason)

                if response.status_code >= 500:
                    retry_reason = f"transient status {response.status_code}: {response.text[:200]}"
                    raise RuntimeError(retry_reason)

                if 400 <= response.status_code < 500:
                    _get_module_logger().error(
                        "Telegram API returned permanent client error %s: %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return False

                try:
                    result = response.json()
                except ValueError:
                    retry_reason = "Telegram API returned a non-JSON response"
                    raise RuntimeError(retry_reason)

                if result.get("ok", False):
                    return True

                error_code = int(result.get("error_code") or 0)
                if error_code == 429:
                    retry_reason = f"rate-limited by Telegram: {result}"
                    raise RuntimeError(retry_reason)

                _get_module_logger().error("Telegram API reported a non-retryable error: %s", result)
                return False
            except requests.exceptions.Timeout as exc:
                retry_reason = f"request timeout after {self.timeout_seconds}s: {exc}"
            except requests.exceptions.ConnectionError as exc:
                retry_reason = f"connection error: {exc}"
            except requests.exceptions.RequestException as exc:
                retry_reason = f"request error: {exc}"
            except RuntimeError as exc:
                retry_reason = str(exc)

            if attempt >= self.retry_max_attempts:
                _get_module_logger().error(
                    "Telegram message failed after %s attempts: %s",
                    self.retry_max_attempts,
                    retry_reason,
                )
                return False

            _get_module_logger().warning(
                "Telegram attempt %s/%s failed (%s). Retrying in %.2f seconds.",
                attempt,
                self.retry_max_attempts,
                retry_reason,
                retry_delay,
            )
            time.sleep(retry_delay)
            retry_delay *= self.retry_backoff_factor

        return False

    def send_threshold_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold_value: float,
        culprit_processes: List[Dict[str, Any]] | None = None,
    ) -> bool:
        """Send a formatted threshold alert with metric context.

        Args:
            metric_name: Short name like 'cpu', 'ram', or 'disk'.
            current_value: Current observed value in percent.
            threshold_value: Configured threshold in percent.
            culprit_processes: Optional list of top CPU/RAM processes.
        """
        normalized = metric_name.lower().replace("_percent", "")

        label_map = {
            "cpu": "CPU",
            "ram": "RAM",
            "disk": "Disk",
        }
        emoji_map = {
            "cpu": "⚠️",
            "ram": "⚠️",
            "disk": "⚠️",
        }

        label = label_map.get(normalized, metric_name.upper())
        emoji = emoji_map.get(normalized, "⚠️")

        lines = [
            f"{emoji} High {label} Alert: {current_value:.2f}%",
            f"Threshold: {threshold_value:.2f}%",
            "Action recommended: investigate the server workload.",
        ]

        if culprit_processes:
            lines.append("")
            lines.append("Top resource-heavy processes:")
            for process in culprit_processes:
                lines.append(
                    "- PID {pid} | {name} | CPU {cpu:.2f}% | RAM {ram:.2f}%".format(
                        pid=process.get("pid", "?"),
                        name=process.get("name", "<unknown>"),
                        cpu=float(process.get("cpu_percent", 0.0)),
                        ram=float(process.get("memory_percent", 0.0)),
                    )
                )

        message = "\n".join(lines)

        return self.send_message(message)

    def send_recovery_alert(self, metric_name: str, current_value: float, threshold_value: float) -> bool:
        """Send a recovery notification once a metric falls below threshold."""
        normalized = metric_name.lower().replace("_percent", "")
        label_map = {
            "cpu": "CPU",
            "ram": "RAM",
            "disk": "Disk",
        }
        label = label_map.get(normalized, metric_name.upper())

        message = (
            f"✅ System Recovered: {label} back to normal ({current_value:.2f}%).\n"
            f"Alert threshold: {threshold_value:.2f}%"
        )

        return self.send_message(message)
