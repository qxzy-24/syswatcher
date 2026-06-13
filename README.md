# 🛡️ Syswatcher

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status: Active](https://img.shields.io/badge/Status-Active-success.svg)

Syswatcher is a lightweight, resilient Python daemon for 24/7 host monitoring with Telegram alerting.
It continuously tracks CPU, RAM, and disk usage, enriches alerts with top resource-heavy processes,
and is built to keep running safely under real production conditions.

---

## 🌟 Features

- **Precise Alert Tuning:** Per-metric thresholds and cooldowns.
- **Recovery Notifications:** Get notified when systems return to normal.
- **Resilient Delivery:** Exponential backoff retries for transient Telegram failures and precise handling of rate limits.
- **Persistent State:** On-disk alert state ensures cooldowns survive process restarts.
- **Cross-Platform:** Configurable log and state paths for Linux and Windows portability.
- **Secure by Design:** Supports secret overrides via `.env` files to prevent committing tokens to source control.
- **Clean Architecture:** Refactored into a proper package with a robust unit test suite.
- **Production Ready:** systemd unit included for Ubuntu server deployments.

## 🏗️ Architecture

Syswatcher is structured as a proper Python package under `src/syswatcher/` implementing clear separation of concerns:

- `src/syswatcher/__init__.py`: Package version and metadata.
- `src/syswatcher/__main__.py`: Module entry point allowing execution via `python -m syswatcher`.
- `src/syswatcher/models.py`: Configuration and runtime state data models.
- `src/syswatcher/config.py`: Configuration loading, validation, and secret injection from env/dotenv.
- `src/syswatcher/logging.py`: Rotating file logger with console fallback.
- `src/syswatcher/monitor.py`: System metric collection and process tracking.
- `src/syswatcher/notifier.py`: Telegram API integration with retries and rate limiting.
- `src/syswatcher/alerting.py`: Core threshold evaluation logic.
- `src/syswatcher/daemon.py`: Main daemon execution loop and signal handling.
- `main.py`: Backward compatibility entry point wrapper.

## 📂 Project Structure

```text
syswatcher/
├── src/
│   └── syswatcher/
│       ├── __init__.py
│       ├── __main__.py
│       ├── alerting.py
│       ├── config.py
│       ├── daemon.py
│       ├── logging.py
│       ├── models.py
│       ├── monitor.py
│       └── notifier.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_alerting.py
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_models.py
│   └── test_state.py
├── config.yaml
├── main.py
├── pyproject.toml
├── requirements.txt
├── syswatch.service
└── README.md
```

## ⚙️ Requirements

- Python 3.10 or later
- Linux (recommended for service mode) or Windows (manual/background mode)

Python dependencies are managed via `pyproject.toml` and listed in `requirements.txt`:
- `psutil`
- `PyYAML`
- `requests`
- `python-dotenv`

---

## 🚀 Quick Start

1. **Clone the repository:**

```bash
git clone https://github.com/qxzy-24/syswatcher.git
cd syswatcher
```

2. **Create and activate a virtual environment:**

*Linux/macOS:*
```bash
python -m venv .venv
source .venv/bin/activate
```

*Windows PowerShell:*
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. **Install the package in editable mode:**

```bash
pip install -e .
```
For development tools (like pytest):
```bash
pip install -e ".[dev]"
```

4. **Configure Secrets via `.env` file:**

Instead of putting your private credentials directly inside `config.yaml`, create a `.env` file in the root directory:

```env
SYSWATCH_BOT_TOKEN="123456789:REPLACE_WITH_TELEGRAM_BOT_TOKEN"
SYSWATCH_CHAT_ID="REPLACE_WITH_CHAT_ID"
```

*Note: Environment variables automatically override values specified in `config.yaml`.*

5. **Start locally:**

```bash
python -m syswatcher
```
*(Or use the backward-compatibility shim: `python main.py`)*

---

## 🧪 Running Tests

To run the unit test suite:

```bash
pytest -v
```

---

## Ubuntu systemd Deployment

Example production layout:

- Application directory: `/opt/syswatch`
- Service file: `/etc/systemd/system/syswatch.service`
- Optional environment overrides: `/etc/default/syswatch`

Deployment steps:

```bash
sudo mkdir -p /opt/syswatch
sudo cp -r . /opt/syswatch/
cd /opt/syswatch
sudo pip3 install -e .
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
- `telegram.bot_token`: Telegram bot token (overridden by `SYSWATCH_BOT_TOKEN`)
- `telegram.chat_id`: Telegram destination chat (overridden by `SYSWATCH_CHAT_ID`)
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

## Security Notes

- Never commit real Telegram credentials to version control. Always use the `.env` override mechanism.
- Keep production `config.yaml` and `.env` files readable only by trusted users.
- Limit service account permissions to required paths.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
