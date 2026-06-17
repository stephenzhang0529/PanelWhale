#!/usr/bin/env bash
#
# postinst.sh — Runs after PanelWhale .deb is installed
#
# NOTE: This runs as root during `sudo apt install`. systemctl --user
# commands cannot reach the user's D-Bus session from here, so we do
# file-level cleanup only, and let the user enable/start manually.
#
set -euo pipefail

APP_DIR="/opt/panelwhale"
SERVICE_DIR_TEMPLATE="$APP_DIR/panelwhale.service"

echo "========================================"
echo " PanelWhale v2.0 — Post-install"
echo "========================================"

# ---- Figure out the real user ------------------------------------------
_REAL_USER=""
_REAL_HOME=""
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    _REAL_USER="$SUDO_USER"
    _REAL_HOME=$(getent passwd "$_REAL_USER" | cut -d: -f6)
elif [ -n "${PKEXEC_UID:-}" ]; then
    _REAL_USER=$(id -nu "$PKEXEC_UID" 2>/dev/null || echo "")
    [ -n "$_REAL_USER" ] && _REAL_HOME=$(getent passwd "$_REAL_USER" | cut -d: -f6)
fi

# ---- Clean up old deepseek-monitor (v1.x) service files -----------------
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

# ---- Remove old /opt/deepseek-monitor -----------------------------------
if [ -d "/opt/deepseek-monitor" ]; then
    rm -rf "/opt/deepseek-monitor"
    echo "✓ Removed old /opt/deepseek-monitor/"
fi

# ---- Install service file for the real user -----------------------------
if [ -n "$_REAL_HOME" ] && [ -d "$_REAL_HOME" ]; then
    _SVC_DIR="$_REAL_HOME/.config/systemd/user"
    mkdir -p "$_SVC_DIR"
    cp "$SERVICE_DIR_TEMPLATE" "$_SVC_DIR/panelwhale.service"
    echo "✓ Service file installed for user '$_REAL_USER'"
else
    # fallback: install for all human users
    for _H in /home/*; do
        [ -d "$_H" ] || continue
        _U=$(basename "$_H")
        _D="$_H/.config/systemd/user"
        mkdir -p "$_D"
        cp "$SERVICE_DIR_TEMPLATE" "$_D/panelwhale.service"
        echo "✓ Service file installed for user '$_U'"
    done
fi

echo ""
echo "========================================"
echo " Install complete!"
echo ""
echo " To start PanelWhale now, run:"
echo "   systemctl --user daemon-reload"
echo "   systemctl --user enable --now panelwhale.service"
echo ""
echo " You should see the PanelWhale icon in your top panel."
echo "========================================"
