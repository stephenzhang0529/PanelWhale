#!/usr/bin/env bash
#
# uninstall.sh — Remove DeepSeek API Usage Monitor
#
#   chmod +x uninstall.sh && ./uninstall.sh
#
set -euo pipefail

APP_DIR="/opt/deepseek-monitor"
USER_CFG_DIR="${HOME}/.config/deepseek-monitor"
DATA_DIR="${HOME}/.local/share/deepseek-monitor"
SERVICE_FILE="${HOME}/.config/systemd/user/deepseek-monitor.service"
AUTOSTART_FILE="${HOME}/.config/autostart/deepseek-monitor.desktop"

echo "========================================"
echo " DeepSeek API Monitor — Uninstaller"
echo "========================================"
echo ""

# ---- 1. Stop & disable systemd service ---------------------------------------
echo "→ Stopping and disabling systemd service …"
systemctl --user stop deepseek-monitor.service 2>/dev/null && echo "  Service stopped." || echo "  No running service."
systemctl --user disable deepseek-monitor.service 2>/dev/null || true
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "✓ Service file removed."
fi
systemctl --user daemon-reload 2>/dev/null || true

# ---- 2. Remove autostart desktop file ----------------------------------------
if [ -f "$AUTOSTART_FILE" ]; then
    rm -f "$AUTOSTART_FILE"
    echo "✓ Autostart entry removed."
fi

# ---- 3. Kill any lingering process --------------------------------------------
pkill -f "python3.*deepseek.*main.py" 2>/dev/null && echo "✓ Process killed." || echo "  No lingering process."

# ---- 4. Remove application ----------------------------------------------------
if [ -d "$APP_DIR" ]; then
    sudo rm -rf "$APP_DIR"
    echo "✓ Application directory removed."
fi

# ---- 5. Remove config ---------------------------------------------------------
if [ -d "$USER_CFG_DIR" ]; then
    read -rp "→ Remove config at $USER_CFG_DIR? [y/N] " CONFIRM
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
        rm -rf "$USER_CFG_DIR"
        echo "✓ Config removed."
    else
        echo "  Config kept."
    fi
fi

# ---- 6. Remove data -----------------------------------------------------------
if [ -d "$DATA_DIR" ]; then
    read -rp "→ Remove balance history at $DATA_DIR? [y/N] " CONFIRM
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
        rm -rf "$DATA_DIR"
        echo "✓ Data removed."
    else
        echo "  Data kept."
    fi
fi

echo ""
echo "========================================"
echo " Uninstall complete."
echo "========================================"
