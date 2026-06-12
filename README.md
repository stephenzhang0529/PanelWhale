<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-Ubuntu%2020.04--26.04-orange.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/memory-~25MB-lightgrey.svg" alt="Memory">
</p>

# 🐋 PanelWhale

[![en](https://img.shields.io/badge/lang-English-blue.svg)](README.md)
[![zh-CN](https://img.shields.io/badge/语言-中文-red.svg)](README_CN.md)

A lightweight Ubuntu desktop app that displays your [DeepSeek](https://platform.deepseek.com) API balance in the top-panel status bar, with consumption stats, low-balance alerts, and persistent session logs.

<p align="center">
  <b>💎 ¥108.32</b> &nbsp;·&nbsp; <b>🟡 ¥4.50</b> &nbsp;·&nbsp; <b>🔴 ¥0.80</b>
</p>

## ✨ Features

- **Panel indicator** — balance shown directly in the GNOME top bar, always visible
- **Right-click menu** — view balance breakdown, consumption over 5 min / 30 min / 3 hours, and today's total
- **Low-balance alerts** — 🟡 yellow at ≤¥5, 🔴 red at ≤¥1; desktop notification on threshold crossing
- **Persistent logs** — per-session consumption saved as local JSON; today's total survives reboots
- **Graceful shutdown** — one last API query on exit / shutdown, with forced flush as fallback
- **systemd-managed** — runs independently of any terminal; auto-restarts on crash; starts on boot
- **Resource-friendly** — ~25 MB RAM, zero CPU when idle

## 🖥️ Compatibility

| Ubuntu Release | GNOME Version | Supported |
|---------------|--------------|-----------|
| 20.04 LTS | 3.36 | ✅ |
| 22.04 LTS | 42 | ✅ |
| 24.04 LTS | 46 | ✅ |
| 26.04 LTS | 48 | ✅ |

Auto-detects AppIndicator3 vs. AyatanaAppIndicator3 at import time.

## 📁 Project Structure

```
~/Desktop/api_monitor/
├── main.py                       # Entry point
├── config.yaml                    # Config template
├── deepseek-monitor.service       # systemd user service
├── install.sh                     # One-shot installer
├── uninstall.sh                   # Uninstaller
└── monitor/
    ├── config.py                  # Config loader (YAML + env vars)
    ├── api.py                     # DeepSeek API client
    ├── store.py                   # Balance history + log persistence
    └── indicator.py               # Panel icon, menu, alert notifications

~/.local/share/deepseek-monitor/logs/   # Runtime logs (auto-created)
~/.config/deepseek-monitor/config.yaml  # User configuration
```

## 🚀 Installation

```bash
cd ~/Desktop/api_monitor
chmod +x install.sh
./install.sh
```

The installer handles everything automatically:
1. Detects your Ubuntu release and installs system dependencies
2. Copies the app to `/opt/deepseek-monitor/`
3. Prompts for your DeepSeek API key
4. Installs and enables the systemd user service (auto-start on login)
5. Starts the monitor immediately

> `sudo` is required for installing system packages. The app itself runs as a normal user.

## ⚙️ Configuration

Edit `~/.config/deepseek-monitor/config.yaml`:

```yaml
api_key: "sk-your-api-key-here"
poll_interval_seconds: 300          # Polling interval in seconds (min: 30)
alert_threshold_yellow: 5.0         # ≤5 → yellow alert
alert_threshold_red: 1.0            # ≤1 → red alert
```

Or use environment variables:

```bash
export DEEPSEEK_API_KEY="sk-xxx"
```

Restart after changing config: `systemctl --user restart deepseek-monitor`

## 📖 Usage

### Everyday Commands

```bash
systemctl --user status   deepseek-monitor   # Check status
systemctl --user stop     deepseek-monitor   # Stop
systemctl --user start    deepseek-monitor   # Start
systemctl --user restart  deepseek-monitor   # Restart
journalctl --user -u deepseek-monitor -f     # Follow logs
```

### Right-Click Menu

Right-click the balance icon in the top panel:

```
────────── 💰 Balance ──────────
Total: ¥108.32
  ├ Topped-up: ¥100.00
  └ Granted:   ¥8.32
────────── 📊 Consumption ──────────
Last 5 min:  ¥0.00
Last 30 min: ¥0.32
Last 3 hr:   ¥1.68
Today:       ¥5.20
──────────────────────────────────
Last update: 2026-06-11 15:30:00
──────────────────────────────────
❌ Quit
```

### Icon Colors

| Icon | Balance | Meaning |
|------|---------|---------|
| 💎 | > ¥5 | Normal |
| 🟡 | ¥1 – ¥5 | Running low |
| 🔴 | < ¥1 | Critically low — top up immediately |
| ⚠️ | — | Network error or invalid API key |

## 🔄 Data Flow

```
Every 5 min → GET /user/balance
                  │
                  ▼
          ┌── success ──→ compute consumption → append log entry → update UI
          │
          └── failure ──→ show ⚠️ → retry next cycle

Exit / Shutdown
    │
    ├── try one last API call
    │   ├─ success → record final consumption → write SUM to log
    │   └─ failure → force-flush accumulated data to log
    │
    └── next startup → scan today's logs → restore today's total
```

## 📊 Log Persistence

Each session's consumption is stored as a JSON file:

```
~/.local/share/deepseek-monitor/logs/
├── 2026-06-11T09-30-00+08-00.json   # Morning session
└── 2026-06-11T14-15-00+08-00.json   # Afternoon session
```

Log file structure:

```json
{
  "session_start": "2026-06-11T14:15:00+08:00",
  "entries": [
    {"ts": "2026-06-11T14:20:00", "consumption": 0.50, "balance": 107.82},
    {"ts": "2026-06-11T14:25:00", "consumption": 0.32, "balance": 107.50}
  ],
  "session_end": "2026-06-11T14:27:30+08:00",
  "sum_consumption": 0.82
}
```

- Logs are kept for 7 days; older files are cleaned up automatically
- "Today" = sum of `sum_consumption` from all of today's log files + current session's consumption so far

## ❓ FAQ

<details>
<summary><b>No icon in the status bar?</b></summary>

```bash
systemctl --user status deepseek-monitor
journalctl --user -u deepseek-monitor -n 30
```

Usually caused by a missing or invalid API key.
</details>

<details>
<summary><b>Icon shows ⚠️ (no connection)?</b></summary>

Network issue or invalid API key. The app retries automatically every polling cycle (5 min). It will recover on its own once the network is back.
</details>

<details>
<summary><b>"Today" resets to 0 after a reboot?</b></summary>

This was a bug in older versions where a failed final API query on shutdown prevented the log from being written. Fixed in the current version — the app now force-flushes accumulated data even when the final query fails.
</details>

<details>
<summary><b>Can I monitor a single API key's usage?</b></summary>

No. DeepSeek's `/user/balance` endpoint returns the **entire account** balance, not per-key usage. All API keys under one account share the same balance pool.
</details>

## 🧹 Uninstall

```bash
cd ~/Desktop/api_monitor
chmod +x uninstall.sh
./uninstall.sh
```

Stops the service, removes the application, and asks whether to keep your config and history.

## 📄 License

MIT
