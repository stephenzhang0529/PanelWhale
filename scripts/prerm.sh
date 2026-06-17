#!/usr/bin/env bash
#
# prerm.sh — Runs before PanelWhale .deb is removed
#
set -euo pipefail

echo "========================================"
echo " PanelWhale — Pre-remove"
echo "========================================"

# ---- Helper: run as a user with D-Bus access ----------------------------
_run_as_user() {
    local _user="$1"; shift
    local _uid
    _uid=$(id -u "$_user" 2>/dev/null || echo "")
    [ -z "$_uid" ] && return 1
    local _run="/run/user/$_uid"
    [ -S "$_run/bus" ] || return 1
    runuser -u "$_user" -- env \
        "XDG_RUNTIME_DIR=$_run" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=$_run/bus" \
        "$@"
}

# ---- Stop, disable, and remove unit files for all human users ------------
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    echo "  Cleaning up for user '$_USER' …"

    # Try stop/disable with D-Bus (best-effort)
    _run_as_user "$_USER" systemctl --user stop panelwhale.service 2>/dev/null || true
    _run_as_user "$_USER" systemctl --user disable panelwhale.service 2>/dev/null || true
    _run_as_user "$_USER" systemctl --user daemon-reload 2>/dev/null || true

    # Remove unit files
    rm -f "$_HOME/.config/systemd/user/panelwhale.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.timer" \
          "$_HOME/.config/systemd/user/deepseek-monitor.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.timer"

    # Kill any lingering panelwhale process for this user
    pkill -u "$_USER" -f "/opt/panelwhale/main.py" 2>/dev/null || true
    pkill -u "$_USER" -f "/opt/deepseek-monitor/main.py" 2>/dev/null || true
done

echo "✓ Ready for removal."
echo "========================================"
