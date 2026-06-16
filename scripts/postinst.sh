#!/usr/bin/env bash
#
# postinst.sh — Runs after PanelWhale .deb is installed
#
set -e

APP_DIR="/opt/panelwhale"
SERVICE_DIR_TEMPLATE="$APP_DIR/panelwhale.service"

echo "========================================"
echo " PanelWhale v2.0 — Post-install"
echo "========================================"

# ---- Clean up old deepseek-monitor (v1.x) ----------------------------
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    _HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    _SVC_DIR="$_HOME/.config/systemd/user"

    # Stop old services
    for OLD in deepseek-monitor.service deepseek-monitor-report.timer; do
        if runuser -u "$SUDO_USER" -- systemctl --user is-enabled --quiet "$OLD" 2>/dev/null; then
            runuser -u "$SUDO_USER" -- systemctl --user stop "$OLD" 2>/dev/null || true
            runuser -u "$SUDO_USER" -- systemctl --user disable "$OLD" 2>/dev/null || true
            echo "  Disabled old $OLD"
        fi
        [ -f "$_SVC_DIR/$OLD" ] && rm -f "$_SVC_DIR/$OLD"
    done

    # Remove deprecated panelwhale report services
    for RPT in panelwhale-report.service panelwhale-report.timer; do
        if runuser -u "$SUDO_USER" -- systemctl --user is-enabled --quiet "$RPT" 2>/dev/null; then
            runuser -u "$SUDO_USER" -- systemctl --user stop "$RPT" 2>/dev/null || true
            runuser -u "$SUDO_USER" -- systemctl --user disable "$RPT" 2>/dev/null || true
        fi
        [ -f "$_SVC_DIR/$RPT" ] && rm -f "$_SVC_DIR/$RPT"
    done

    # Reload user systemd
    runuser -u "$SUDO_USER" -- systemctl --user daemon-reload 2>/dev/null || true

    # Copy service file to user's systemd directory
    mkdir -p "$_SVC_DIR"
    cp "$SERVICE_DIR_TEMPLATE" "$_SVC_DIR/panelwhale.service"

    # Enable and start
    runuser -u "$SUDO_USER" -- systemctl --user daemon-reload
    runuser -u "$SUDO_USER" -- systemctl --user enable panelwhale.service
    runuser -u "$SUDO_USER" -- systemctl --user start panelwhale.service || true

    echo ""
    echo "✓ PanelWhale installed and started for user '$SUDO_USER'."
    echo "  You should see the PanelWhale icon in your top panel."
else
    echo ""
    echo "  To enable autostart for your user, run:"
    echo "    systemctl --user enable --now panelwhale.service"
fi

# Remove old deepseek-monitor directory
if [ -d "/opt/deepseek-monitor" ]; then
    rm -rf "/opt/deepseek-monitor"
    echo "✓ Removed old /opt/deepseek-monitor/"
fi

echo ""
echo "========================================"
echo " Install complete!"
echo "========================================"
