# Development Guide

## Environment

PanelWhale uses GTK 3 and AppIndicator via Python's GObject Introspection
bindings. These are **only available in the system Python** — conda / pyenv /
virtualenv will not work for running the app.

```bash
# Verify your system Python has the required bindings
/usr/bin/python3 -c "
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
print('OK')
"
```

Install system dependencies (Ubuntu):

```bash
sudo apt install python3 python3-gi python3-gi-cairo \
  gir1.2-gtk-3.0 gir1.2-notify-0.7 python3-requests python3-yaml

# Ubuntu 24.04+
sudo apt install gir1.2-ayatanaappindicator3-0.1

# Ubuntu 20.04 / 22.04
sudo apt install gir1.2-appindicator3-0.1 gnome-shell-extension-appindicator
```

## Project Structure

```
PanelWhale/
├── main.py                       # Entry point
├── config.yaml                    # Config template
├── install.sh / uninstall.sh      # One-shot installer / uninstaller
├── systemd/
│   ├── panelwhale.service
│   ├── panelwhale-report.service
│   └── panelwhale-report.timer
├── scripts/
│   ├── generate_weekly_report.py  # [prod] Called by systemd timer
│   ├── generate_fake_data.py      # [dev]  Generate fake API usage data
│   └── test_balance_display.py    # [dev]  Test balance indicator colours
└── monitor/
    ├── config.py                  # Config loader (YAML + env vars)
    ├── api.py                     # DeepSeek API client
    ├── store.py                   # Balance history + log persistence
    ├── indicator.py               # Panel icon, menu, notifications
    ├── report.py                  # Daily summary store + report generator
    └── report_template.html       # ECharts HTML template for weekly reports
```

### Data directories (runtime)

```
~/.local/share/panelwhale/
├── logs/               # Raw session logs (30-day retention)
├── daily_summaries/    # Per-day aggregates (365-day retention)
├── reports/            # Weekly HTML reports (permanent)
└── currency            # Last-seen currency code from API
```

---

## Debugging Workflow

### 1. Stop the background service

The systemd service runs the monitor continuously. Stop it before manual
debugging:

```bash
systemctl --user stop panelwhale
```

When you're done, restart it:

```bash
systemctl --user start panelwhale
```

### 2. Run the monitor manually

```bash
cd PanelWhale
/usr/bin/python3 main.py
```

You'll see log output on stdout and the panel icon in the status bar.
Press `Ctrl+C` or right-click → Quit to exit.

---

## Testing with Fake Data

### Fake API usage data

`scripts/generate_fake_data.py` creates ~12 days of realistic session logs
under `~/.local/share/panelwhale/logs/` with:
- Weekday usage heavier than weekends
- Peak hours around 10am and 3pm
- Multiple sessions per day

```bash
/usr/bin/python3 scripts/generate_fake_data.py
```

### Test balance indicator colours

`scripts/test_balance_display.py` runs the full panel indicator against a
mock API that returns a fixed balance — no real API key needed, no disk
writes.

```bash
# Single balance
/usr/bin/python3 scripts/test_balance_display.py 0.80   # red
/usr/bin/python3 scripts/test_balance_display.py 3.50   # yellow
/usr/bin/python3 scripts/test_balance_display.py 108.00 # normal

# Cycle through all 3 states (10 seconds each)
/usr/bin/python3 scripts/test_balance_display.py
```

Expected panel label:

| Balance | Display       | State   |
|---------|---------------|---------|
| > ¥5    | `¥108.32`     | Normal  |
| ¥1–5    | `🟡 ¥3.50`   | Warning |
| < ¥1    | `🔴 ¥0.80`   | Danger  |
| Error   | `⚠️ No Connection` | Error |

The right-click menu also changes: a **Charge** button appears when balance
is ≤ ¥5, linking to `https://platform.deepseek.com/top_up`.

### Test weekly report generation

1. Generate fake data (covers a complete Mon–Sun week)
2. Run the report generator

```bash
/usr/bin/python3 scripts/generate_fake_data.py
/usr/bin/python3 scripts/generate_weekly_report.py
```

The report is saved to `~/.local/share/panelwhale/reports/`.
Open it:

```bash
xdg-open ~/.local/share/panelwhale/reports/report_2026-06-01.html
```

If you need to re-run (the generator skips weeks that already have reports):

```bash
rm -f ~/.local/share/panelwhale/reports/report_2026-06-01.html
rm -f ~/.local/share/panelwhale/daily_summaries/2026-06-*.json
/usr/bin/python3 scripts/generate_weekly_report.py
```

---

## End-to-End Testing with `install.sh`

To test the full install → run → uninstall cycle:

```bash
# 1. Install to /opt/panelwhale/
sudo ./install.sh

# 2. Verify the service is running
systemctl --user status panelwhale
systemctl --user status panelwhale-report.timer

# 3. Check the panel — the DeepSeek icon should appear in the status bar

# 4. Manually trigger the report timer
systemctl --user start panelwhale-report.service

# 5. Verify reports
ls ~/.local/share/panelwhale/reports/

# 6. Uninstall
./uninstall.sh
```

> **Note:** The installer copies files to `/opt/`. If you make code changes
> and want to test them in the installed version, you must re-run
> `sudo ./install.sh` or manually copy the changed files.

---

## Common Issues

### "No module named gi"

You are using a non-system Python (conda, pyenv, venv).
Use `/usr/bin/python3` instead.

### "No icon in the status bar"

```bash
systemctl --user status panelwhale
journalctl --user -u panelwhale -n 30
```

Usually a missing or invalid API key. Set it in
`~/.config/panelwhale/config.yaml` or the `DEEPSEEK_API_KEY`
environment variable.

### Changes not taking effect after editing code

If the monitor is running under systemd, restart it:

```bash
systemctl --user restart panelwhale
```

### Report not generating

Check the timer status:

```bash
systemctl --user status panelwhale-report.timer
systemctl --user list-timers
```

Manually trigger:

```bash
systemctl --user start panelwhale-report.service
journalctl --user -u panelwhale-report.service
```

### `generate_weekly_report.py` can't find `monitor.report`

Run from the project root so the import path is correct:

```bash
cd PanelWhale
/usr/bin/python3 scripts/generate_weekly_report.py
```

Or if running from the installed location, it uses `/opt/panelwhale`
as a fallback path.
