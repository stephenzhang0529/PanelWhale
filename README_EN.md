# 🐋 PanelWhale

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/platform-Ubuntu%2020.04--26.04-orange.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/memory-~80MB-lightgrey.svg" alt="Memory">
</p>

[中文文档](README.md)

A lightweight Ubuntu desktop app that displays your [DeepSeek](https://platform.deepseek.com) API balance and usage in the top-panel status bar, with consumption stats, low-balance alerts, per-model token analysis, an interactive control panel, and a GTK settings window.

This project is based on [DeepSeekMonitor](https://github.com/JayHome137/DeepSeekMonitor) and [DeepSeekMonitorWindows](https://github.com/Joyi-code/DeepSeekMonitorWindows), redesigned for Ubuntu with richer features and a better user experience.

## ✨ Features

- **Panel indicator** — balance shown directly in the GNOME top bar, always visible
- **Low-balance alerts** — 🟡 at ≤¥5, 🔴 at ≤¥1; desktop notification on threshold crossing
- **Quick top-up** — a Charge button appears in the right-click menu when balance ≤¥5, linking to the DeepSeek top-up page
- **Usage stats** — after configuring a Usage Token, the right-click menu shows MTD total cost and per-model (Flash / Pro) token volume and cache hit rate
- **Right-click menu** — view balance breakdown, recent consumption, today's total, and monthly usage
- **Control Panel** — interactive 3-column HTML dashboard with balance card, model rows, cache-hit stacked bar chart, daily/hourly consumption line charts, and Flash / Pro detail pages
- **Settings window** — GTK GUI to configure API Key, Usage Token, polling intervals, alert thresholds, and autostart
- **Persistent logs** — per-session consumption saved as JSON; today's total survives reboots
- **systemd-managed** — runs independently of any terminal; auto-restarts on crash; starts on boot
- **Resource-friendly** — ~80 MB RAM, zero CPU when idle

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
PanelWhale/
├── main.py
├── config.yaml
├── install.sh / uninstall.sh
├── systemd/
│   └── panelwhale.service
├── scripts/
│   ├── generate_fake_data.py      # Generate test data
│   └── test_balance_display.py    # Test indicator colors
└── monitor/
    ├── config.py                  # Config loader / saver
    ├── api.py                     # DeepSeek balance API client
    ├── usage_api.py               # Platform usage / cost API client
    ├── usage_cache.py             # Usage data cache
    ├── store.py                   # Balance history + session logs
    ├── indicator.py               # Panel icon, menu, notifications
    ├── report.py                  # Daily consumption summaries
    ├── panel.py                   # Control panel HTML generator
    ├── settings.py                # GTK settings window
    ├── panel_template.html        # Control panel HTML template
    └── deepseek-color.png         # DeepSeek logo icon
```

### Runtime Data Directories

```
~/.local/share/panelwhale/
├── logs/               # Raw session logs (30-day retention)
├── daily_summaries/    # Daily aggregates (365-day retention)
├── panel/              # Generated control panel HTML
├── usage_cache.json    # Usage data cache
└── currency            # Last-seen currency code from API
```

## 🚀 Installation

```bash
cd PanelWhale
chmod +x install.sh
./install.sh
```

The installer handles everything automatically:
1. Detects your Ubuntu release and installs system dependencies
2. Copies the app to `/opt/panelwhale/`
3. Prompts for your DeepSeek API key
4. Installs and enables the systemd user service (auto-start on login)
5. Starts the monitor immediately

> `sudo` is required for installing system packages. The app itself runs as a normal user.

## ⚙️ Configuration

Configure via right-click → **Settings**, or edit `~/.config/panelwhale/config.yaml`:

```yaml
api_key: "sk-your-api-key-here"

# Usage Token (optional) — log into platform.deepseek.com and run in the
# browser console: JSON.parse(localStorage.userToken).value
usage_token: ""

poll_interval_seconds: 300          # Balance poll interval (seconds, min: 30)
usage_poll_interval_seconds: 3600   # Usage poll interval (seconds, min: 600)
alert_threshold_yellow: 5.0         # ≤5 → yellow alert
alert_threshold_red: 1.0            # ≤1 → red alert
```

Or use environment variables: `DEEPSEEK_API_KEY`, `DEEPSEEK_USAGE_TOKEN`. Restart after changes:

```bash
systemctl --user restart panelwhale
```

## 📖 Usage

```bash
# Everyday management
systemctl --user status   panelwhale   # Check status
systemctl --user stop     panelwhale   # Stop
systemctl --user start    panelwhale   # Start
systemctl --user restart  panelwhale   # Restart
journalctl --user -u panelwhale -f     # Follow logs
```

### Right-Click Menu

```
Total Balance: ¥108.32
  Topped-up: ¥100.00
  Granted: ¥8.32
──────────────
Last 5 min:  ¥0.00
Last 30 min: ¥0.32
Last 3 hr:   ¥1.68
Today:       ¥5.20
──────────────
Usage This Month              ← shown when Usage Token is configured
  Total Cost: ¥12.50
  Flash: 944K tokens (96% cache hit) - ¥5.20
  Pro: 12.7M tokens (84% cache hit) - ¥7.30
──────────────
Last update: ...
──────────────
Charge                        ← appears when ≤¥5
──────────────
Refresh
──────────────
Settings                      ← GTK settings window
──────────────
Open Control Panel            ← 3-column interactive dashboard
──────────────
Quit
```

### Control Panel

Right-click → **Open Control Panel** opens a 3-column dashboard in your browser:

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Balance card | Daily consumption line chart | Flash detail |
| Flash / Pro model rows | Hourly average line chart | Pro detail |
| Cache hit stacked bar | | |

## ❓ FAQ

<details>
<summary><b>No icon in the status bar?</b></summary>

```bash
systemctl --user status panelwhale
journalctl --user -u panelwhale -n 30
```

Usually caused by a missing or invalid API key.
</details>

<details>
<summary><b>Icon shows ⚠️ No Connection?</b></summary>

Network issue or invalid API key. The app retries automatically on the next poll cycle.
</details>

<details>
<summary><b>How to see per-model usage (Flash / Pro)?</b></summary>

1. Log into https://platform.deepseek.com in your browser
2. Press F12 → Console, run `JSON.parse(localStorage.userToken).value`
3. Copy the output token into `usage_token` in `~/.config/panelwhale/config.yaml`
4. Restart: `systemctl --user restart panelwhale`
5. "Usage This Month" appears in the menu; model details appear in the Control Panel

You can also paste the token in the Settings window (right-click → **Settings**).
</details>

<details>
<summary><b>Today's total reset to 0 after reboot?</b></summary>

This was caused by a failed final API poll during shutdown. The current version forces a flush to disk even on failure, preserving existing data.
</details>

<details>
<summary><b>Can I monitor a single API key's usage?</b></summary>

No. DeepSeek's `/user/balance` endpoint returns the entire account balance. All API keys under one account share the same balance pool.
</details>

## 🧹 Uninstall

```bash
cd PanelWhale
chmod +x uninstall.sh
./uninstall.sh
```

Stops the service, removes application files, and asks whether to keep your config and history.

## 🧪 Development & Testing

```bash
# Stop the background service first
systemctl --user stop panelwhale

# Generate 12 days of fake data
/usr/bin/python3 scripts/generate_fake_data.py

# Test indicator colors
/usr/bin/python3 scripts/test_balance_display.py 0.80   # red
/usr/bin/python3 scripts/test_balance_display.py 3.50   # yellow
/usr/bin/python3 scripts/test_balance_display.py        # cycle all 3 states
```

## 📄 License

MIT
