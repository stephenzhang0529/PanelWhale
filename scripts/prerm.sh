#!/usr/bin/env bash
#
# prerm.sh — Runs before PanelWhale .deb is removed
#
# NOTE: This runs as root during `sudo apt remove`. systemctl --user
# commands cannot reach the user's D-Bus session. We do file-level
# cleanup only; the user should run `systemctl --user stop/disable` first.
#
set -euo pipefail

echo "========================================"
echo " PanelWhale — Pre-remove"
echo "========================================"

# Remove service files for all human users (best-effort)
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    echo "  Cleaning up services for user '$_USER' …"

    # Try stop/disable (may fail if D-Bus unavailable — that's OK)
    runuser -u "$_USER" -- systemctl --user stop panelwhale.service 2>/dev/null || true
    runuser -u "$_USER" -- systemctl --user disable panelwhale.service 2>/dev/null || true
    runuser -u "$_USER" -- systemctl --user daemon-reload 2>/dev/null || true

    # Remove unit files
    rm -f "$_HOME/.config/systemd/user/panelwhale.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.timer" \
          "$_HOME/.config/systemd/user/deepseek-monitor.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.timer"
done

echo "✓ Ready for removal."
echo "========================================"
