# Changelog

All notable changes to this project will be documented in this file.

## [1.0.2] - 2026-06-08

### Fixed
- Fixed premature logger initialization in `notifier.py` that could create handlers before the daemon configured logging.
- Fixed per-process CPU measurements returning near-zero values by reordering counter priming before the 1-second system CPU sample.
- Corrected Python version requirement from 3.8+ to 3.10+ (codebase uses PEP 604 union syntax).

### Added
- Graceful shutdown handling via SIGTERM/SIGINT with final state persistence.
- Segmented sleep in the daemon loop so signals are handled within 1 second.
- Python 3.13 added to the CI test matrix.
- Minimum version constraints in `requirements.txt`.

### Changed
- systemd unit now sets `WorkingDirectory` to the application directory.
- systemd unit documents how to run as a non-root dedicated service user.
- systemd unit adds `KillMode=mixed` and `TimeoutStopSec=30` for graceful shutdown.

## [1.0.1] - 2026-06-08

### Fixed
- Fixed Telegram rate limiting to respect the exact `retry_after` duration provided by the API instead of using exponential backoff.
- Gracefully handle missing `config.yaml` with a clear, readable error message.
- Optimized logger initialization to prevent redundant reconfiguration.

### Changed
- Updated Telegram API requests to use the modern `link_preview_options` instead of the deprecated `disable_web_page_preview`.

## [1.0.0] - 2026-03-31

### Added

- Core 24/7 monitoring daemon for CPU, RAM, and disk thresholds
- Telegram alerting with exponential backoff retries
- Recovery notifications when metrics return below threshold
- Per-metric threshold and cooldown configuration
- Persisted runtime state to preserve cooldown behavior across restarts
- Configurable disk mountpoint monitoring and top-process enrichment
- Rotating file logging with configurable path support
- systemd unit for Ubuntu service deployment
