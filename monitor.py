"""System metric collection utilities for syswatch.

The functions in this module use psutil to read real-time host metrics in a
lightweight way that is suitable for frequent polling.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import psutil


def _get_default_mountpoint() -> str:
    """Return a best-effort default mount point for disk monitoring.

    On Linux, '/' is preferred. On Windows, the system drive is preferred when
    available. If no preferred target is found, the first mounted partition is
    used as a defensive fallback.
    """
    partitions = psutil.disk_partitions(all=False)

    for partition in partitions:
        if partition.mountpoint == "/":
            return partition.mountpoint

    system_drive = os.environ.get("SystemDrive")
    if system_drive:
        preferred_windows_mount = f"{system_drive}\\"
        for partition in partitions:
            if partition.mountpoint.lower() == preferred_windows_mount.lower():
                return partition.mountpoint

    if partitions:
        return partitions[0].mountpoint

    # Defensive fallback for edge cases where partition listing is unavailable.
    return "/"


def _resolve_mountpoint(configured_mountpoint: str | None) -> str:
    """Resolve a user-configured mountpoint, supporting an automatic mode."""
    if configured_mountpoint and configured_mountpoint.lower() != "auto":
        return configured_mountpoint

    return _get_default_mountpoint()


def _prime_process_cpu_counters() -> None:
    """Prime per-process CPU counters for meaningful next-sample percentages."""
    for process in psutil.process_iter(attrs=[]):
        try:
            process.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def _get_top_processes(limit: int) -> Dict[str, List[Dict[str, Any]]]:
    """Return top CPU and RAM processes for alert enrichment."""
    rows: List[Dict[str, Any]] = []

    for process in psutil.process_iter(attrs=["pid", "name", "memory_percent"]):
        try:
            info = process.info
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": (info.get("name") or "<unknown>").strip() or "<unknown>",
                    "cpu_percent": round(process.cpu_percent(interval=None), 2),
                    "memory_percent": round(float(info.get("memory_percent") or 0.0), 2),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    top_cpu = sorted(rows, key=lambda row: row["cpu_percent"], reverse=True)[:limit]
    top_ram = sorted(rows, key=lambda row: row["memory_percent"], reverse=True)[:limit]

    return {
        "cpu": top_cpu,
        "ram": top_ram,
    }


def get_system_metrics(disk_mountpoint: str | None = None, top_process_count: int = 3) -> Dict[str, Any]:
    """Fetch current CPU, RAM, Disk, and Network metrics.

    Returns:
        Dict[str, Any]: A normalized snapshot suitable for threshold checks and
        logging. Percent values are rounded for readability.
    """
    # Prime per-process CPU counters *before* the blocking system CPU call.
    # The 1-second `interval` in `cpu_percent()` then doubles as the time
    # window for meaningful per-process CPU deltas.
    _prime_process_cpu_counters()

    # interval=1.0 produces a more realistic CPU percentage than an instant call.
    cpu_percent = psutil.cpu_percent(interval=1.0)

    memory = psutil.virtual_memory()

    mountpoint = _resolve_mountpoint(disk_mountpoint)

    try:
        disk = psutil.disk_usage(mountpoint)
    except (FileNotFoundError, PermissionError, OSError):
        # If the configured path is not usable, continue with a safe default.
        mountpoint = _get_default_mountpoint()
        disk = psutil.disk_usage(mountpoint)

    net_io = psutil.net_io_counters()
    top_processes = _get_top_processes(max(top_process_count, 1))

    return {
        "cpu_percent": round(cpu_percent, 2),
        "ram_percent": round(memory.percent, 2),
        "disk_percent": round(disk.percent, 2),
        "disk_mountpoint": mountpoint,
        "top_processes": top_processes,
        "network": {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errin": net_io.errin,
            "errout": net_io.errout,
            "dropin": net_io.dropin,
            "dropout": net_io.dropout,
        },
    }
