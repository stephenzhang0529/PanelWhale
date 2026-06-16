#!/usr/bin/env bash
#
# prerm.sh — Runs before PanelWhale .deb is removed
#
set -e

echo "========================================"
echo " PanelWhale — Pre-remove"
echo "========================================"

# Stop and disable user services for any user that has them
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    _SVC="$_HOME/.config/systemd/user/panelwhale.service"
    if [ -f "$_SVC" ]; then
        runuser -u "$_USER" -- systemctl --user stop panelwhale.service 2>/dev/null || true
        runuser -u "$_USER" -- systemctl --user disable panelwhale.service 2>/dev/null || true
        rm -f "$_SVC"
        runuser -u "$_USER" -- systemctl --user daemon-reload 2>/dev/null || true
        echo "  Stopped and disabled for user '$_USER'"
    fi
done

# Also stop old deepseek-monitor if somehow still present
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    if [ -f "$_HOME/.config/systemd/user/deepseek-monitor.service" ]; then
        runuser -u "$_USER" -- systemctl --user stop deepseek-monitor.service 2>/dev/null || true
        runuser -u "$_USER" -- systemctl --user disable deepseek-monitor.service 2>/dev/null || true
        rm -f "$_HOME/.config/systemd/user/deepseek-monitor.service" \
              "$_HOME/.config/systemd/user/deepseek-monitor-report.service" \
              "$_HOME/.config/systemd/user/deepseek-monitor-report.timer"
        runuser -u "$_USER" -- systemctl --user daemon-reload 2>/dev/null || true
        echo "  Removed old deepseek-monitor services for user '$_USER'"
    fi
done

echo "✓ Ready for removal."
echo "========================================"
