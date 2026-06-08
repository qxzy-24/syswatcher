# Changelog

All notable changes to this project will be documented in this file.

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
