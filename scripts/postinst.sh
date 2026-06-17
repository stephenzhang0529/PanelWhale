#!/usr/bin/env bash
#
# postinst.sh — Runs after PanelWhale .deb is installed
#
set -euo pipefail

APP_DIR="/opt/panelwhale"
SERVICE_FILE="$APP_DIR/panelwhale.service"

echo "========================================"
echo " PanelWhale v2.0 — Post-install"
echo "========================================"

# ---- Find the real user -------------------------------------------------
_REAL_USER=""
_REAL_HOME=""
_REAL_UID=""
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    _REAL_USER="$SUDO_USER"
    _REAL_HOME=$(getent passwd "$_REAL_USER" | cut -d: -f6)
    _REAL_UID=$(id -u "$_REAL_USER" 2>/dev/null || echo "")
elif [ -n "${PKEXEC_UID:-}" ]; then
    _REAL_USER=$(id -nu "$PKEXEC_UID" 2>/dev/null || echo "")
    [ -n "$_REAL_USER" ] && _REAL_HOME=$(getent passwd "$_REAL_USER" | cut -d: -f6)
    [ -n "$_REAL_USER" ] && _REAL_UID="$PKEXEC_UID"
fi

# ---- Helper: run a command as the real user with D-Bus access ------------
_run_as_user() {
    if [ -z "${_REAL_USER:-}" ] || [ -z "${_REAL_UID:-}" ]; then
        return 1
    fi
    local _run="/run/user/$_REAL_UID"
    if [ ! -S "$_run/bus" ]; then
        return 1  # D-Bus socket not available (e.g. SSH session)
    fi
    runuser -u "$_REAL_USER" -- env \
        "XDG_RUNTIME_DIR=$_run" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=$_run/bus" \
        "$@"
}

# ---- Clean up old deepseek-monitor (v1.x) service files ------------------
if [ -n "$_REAL_HOME" ] && [ -d "$_REAL_HOME" ]; then
    _SVC_DIR="$_REAL_HOME/.config/systemd/user"
    for OLD_FILE in \
        "$_SVC_DIR/deepseek-monitor.service" \
        "$_SVC_DIR/deepseek-monitor-report.service" \
        "$_SVC_DIR/deepseek-monitor-report.timer" \
        "$_SVC_DIR/panelwhale-report.service" \
        "$_SVC_DIR/panelwhale-report.timer"; do
        if [ -f "$OLD_FILE" ]; then
            rm -f "$OLD_FILE"
            echo "  Removed $(basename "$OLD_FILE")"
        fi
    done
fi

# ---- Remove old /opt/deepseek-monitor ------------------------------------
if [ -d "/opt/deepseek-monitor" ]; then
    rm -rf "/opt/deepseek-monitor"
    echo "✓ Removed old /opt/deepseek-monitor/"
fi

# ---- Install and start service for the real user -------------------------
if [ -n "$_REAL_HOME" ] && [ -d "$_REAL_HOME" ]; then
    _SVC_DIR="$_REAL_HOME/.config/systemd/user"
    mkdir -p "$_SVC_DIR"
    cp "$SERVICE_FILE" "$_SVC_DIR/panelwhale.service"

    # Try to enable & start via D-Bus
    if _run_as_user systemctl --user daemon-reload 2>/dev/null; then
        _run_as_user systemctl --user enable panelwhale.service 2>/dev/null || true
        # Stop any existing instance first, then start fresh
        _run_as_user systemctl --user stop panelwhale.service 2>/dev/null || true
        _run_as_user systemctl --user start panelwhale.service 2>/dev/null || true

        echo ""
        echo "✓ PanelWhale installed and started for user '$_REAL_USER'."
        echo "  You should see the PanelWhale icon in your top panel."
    else
        echo "✓ Service file installed for user '$_REAL_USER'"
        echo ""
        echo "  To start PanelWhale now, run:"
        echo "    systemctl --user daemon-reload"
        echo "    systemctl --user enable --now panelwhale.service"
    fi
else
    # fallback: install for all human users
    for _H in /home/*; do
        [ -d "$_H" ] || continue
        _U=$(basename "$_H")
        _D="$_H/.config/systemd/user"
        mkdir -p "$_D"
        cp "$SERVICE_FILE" "$_D/panelwhale.service"
        echo "✓ Service file installed for user '$_U'"
    done
    echo ""
    echo "  To start PanelWhale, run:"
    echo "    systemctl --user daemon-reload"
    echo "    systemctl --user enable --now panelwhale.service"
fi

echo ""
echo "========================================"
echo " Install complete!"
echo "========================================"
