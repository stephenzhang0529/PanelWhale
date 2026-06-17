#!/usr/bin/env bash
#
# prerm.sh — Runs before PanelWhale .deb files are removed
#
# Stops the running service and kills lingering processes. Config/data
# cleanup is handled by postrm.
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

# ---- Stop & disable services for all human users ------------------------
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    echo "  Stopping services for user '$_USER' …"

    _run_as_user "$_USER" systemctl --user stop panelwhale.service 2>/dev/null || true
    _run_as_user "$_USER" systemctl --user disable panelwhale.service 2>/dev/null || true
    _run_as_user "$_USER" systemctl --user daemon-reload 2>/dev/null || true

    # Also stop old services just in case
    _run_as_user "$_USER" systemctl --user stop deepseek-monitor.service 2>/dev/null || true
    _run_as_user "$_USER" systemctl --user disable deepseek-monitor.service 2>/dev/null || true

    # Kill lingering processes
    pkill -u "$_USER" -f "/opt/panelwhale/main.py" 2>/dev/null || true
    pkill -u "$_USER" -f "/opt/deepseek-monitor/main.py" 2>/dev/null || true
done

echo "✓ Services stopped."
echo "========================================"
