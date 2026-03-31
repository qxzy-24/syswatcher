# Syswatcher

Syswatcher is a lightweight, resilient Python daemon for 24/7 host monitoring with Telegram alerting.
It continuously tracks CPU, RAM, and disk usage, enriches alerts with top resource-heavy processes,
and is built to keep running safely under real production conditions.

## Why Syswatcher

- Per-metric thresholds and cooldowns for precise alert tuning
- Recovery notifications when systems return to normal
- Exponential backoff retries for transient Telegram failures
- Persistent on-disk alert state so cooldowns survive process restarts
- Configurable log and state paths for Linux and Windows portability
- systemd unit included for Ubuntu server deployments

## Architecture

- `main.py`: daemon loop, config loading, alert policy evaluation, persistent state
- `monitor.py`: psutil-based metric collection and top process sampling
- `notifier.py`: Telegram API integration, retries, alert/recovery message formatting
- `logger.py`: rotating file logger with safe fallback
- `config.yaml`: runtime configuration for thresholds, cooldowns, paths, and retry behavior
- `syswatch.service`: systemd unit for long-running service management

## Project Structure

```text
syswatcher/
├── config.yaml
├── logger.py
├── main.py
├── monitor.py
├── notifier.py
├── requirements.txt
├── syswatch.service
└── README.md
```

## Requirements

- Python 3.8 or later
- Linux (recommended for service mode) or Windows (manual/background mode)

Python dependencies are listed in `requirements.txt`:

- psutil
- PyYAML
- requests

## Quick Start

1. Clone the repository.

```bash
git clone https://github.com/USERNAME/syswatcher.git
cd syswatcher
```

2. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Update `config.yaml` with your Telegram token/chat ID and desired thresholds.

5. Start locally.

```bash
python main.py
```

## Ubuntu systemd Deployment

Example production layout:

- Application directory: `/opt/syswatch`
- Service file: `/etc/systemd/system/syswatch.service`
- Optional environment overrides: `/etc/default/syswatch`

Deployment steps:

```bash
sudo mkdir -p /opt/syswatch
sudo cp -r . /opt/syswatch/
sudo cp /opt/syswatch/syswatch.service /etc/systemd/system/syswatch.service
sudo systemctl daemon-reload
sudo systemctl enable syswatch
sudo systemctl start syswatch
sudo systemctl status syswatch
```

View logs:

```bash
sudo journalctl -u syswatch -f
```

## Configuration Reference

`config.yaml` keys:

- `paths.log_file`: log file location (relative paths resolve from config directory)
- `paths.state_file`: persisted runtime state file for cooldown continuity
- `check_interval_seconds`: polling interval for metric collection
- `monitor.disk_mountpoint`: target disk path (`auto`, `/data`, `C:\\`, etc.)
- `monitor.top_process_count`: number of top CPU/RAM processes in alerts
- `telegram.bot_token`: Telegram bot token
- `telegram.chat_id`: Telegram destination chat
- `telegram.request_timeout_seconds`: HTTP timeout per Telegram request
- `telegram.retry_max_attempts`: maximum send attempts per message
- `telegram.retry_initial_delay_seconds`: initial retry delay
- `telegram.retry_backoff_factor`: retry delay multiplier
- `alerts.cpu.threshold_percent`: CPU alert threshold
- `alerts.cpu.cooldown_minutes`: CPU cooldown window
- `alerts.ram.threshold_percent`: RAM alert threshold
- `alerts.ram.cooldown_minutes`: RAM cooldown window
- `alerts.disk.threshold_percent`: disk alert threshold
- `alerts.disk.cooldown_minutes`: disk cooldown window

## Runtime Behavior

- High metric alert: sent when a metric crosses threshold and cooldown has expired
- Cooldown suppression: repeated alerts for the same metric are muted during cooldown
- Recovery alert: sent once when a previously-alerted metric drops below threshold
- State persistence: cooldown and active-alert state are stored on disk and restored on restart

## Security Notes

- Never commit real Telegram credentials to version control
- Keep production `config.yaml` readable only by trusted users
- Restrict service account permissions to required paths

## Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
python main.py --config ./config.yaml
```

## Repository Standards

- License: MIT
- Contributions: see `CONTRIBUTING.md`
- Security reporting: see `SECURITY.md`
- Changelog: see `CHANGELOG.md`

## License

This project is licensed under the MIT License. See `LICENSE` for details.
