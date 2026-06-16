#!/usr/bin/env bash
#
# install.sh — Install DeepSeek API Usage Monitor
#
#   chmod +x install.sh && ./install.sh
#
set -euo pipefail

APP_DIR="/opt/panelwhale"
USER_CFG_DIR="${HOME}/.config/panelwhale"
DATA_DIR="${HOME}/.local/share/panelwhale"
AUTOSTART_DIR="${HOME}/.config/autostart"

echo "========================================"
echo " DeepSeek API Monitor — Installer"
echo "========================================"
echo ""

# ---- 1. Detect Ubuntu version ------------------------------------------------
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "→ Detected: $NAME $VERSION_ID"
else
    echo "⚠ Could not detect OS; assuming Ubuntu 22.04+"
    VERSION_ID="22.04"
fi

MAJOR_VER="${VERSION_ID%%.*}"

# ---- 2. Install system dependencies ------------------------------------------
echo ""
echo "→ Installing system dependencies (sudo may prompt for password) …"

PKGS="python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-notify-0.7 python3-requests python3-yaml"

if [ "$MAJOR_VER" -ge 24 ]; then
    PKGS="$PKGS gir1.2-ayatanaappindicator3-0.1"
else
    PKGS="$PKGS gir1.2-appindicator3-0.1"
    # GNOME Shell extension for 20.04/22.04
    if [ "$MAJOR_VER" -le 22 ]; then
        PKGS="$PKGS gnome-shell-extension-appindicator"
    fi
fi

sudo apt update -qq
# shellcheck disable=SC2086
sudo apt install -y $PKGS

echo "✓ Dependencies installed."

# ---- 3. Copy application files ------------------------------------------------
echo ""
echo "→ Installing application to $APP_DIR …"
sudo mkdir -p "$APP_DIR"
sudo cp -r "$(dirname "$0")/main.py" \
           "$(dirname "$0")/monitor" \
           "$(dirname "$0")/config.yaml" \
           "$APP_DIR/"
sudo cp "$(dirname "$0")/systemd/panelwhale.service" "$APP_DIR/"
sudo chown -R root:root "$APP_DIR"
sudo chmod -R 755 "$APP_DIR"
echo "✓ Application files copied."

# ---- 4. User config -----------------------------------------------------------
echo ""
mkdir -p "$USER_CFG_DIR"
if [ ! -f "$USER_CFG_DIR/config.yaml" ]; then
    echo "→ Creating user config …"
    cat > "$USER_CFG_DIR/config.yaml" << 'YAMLEOF'
# PanelWhale — configuration
# Environment variable DEEPSEEK_API_KEY overrides the file.

api_key: "sk-your-api-key-here"

# Usage token for platform.deepseek.com internal APIs (OPTIONAL).
# Get it by logging into https://platform.deepseek.com and running in
# the browser's DevTools console:
#   JSON.parse(localStorage.userToken).value
# Environment variable: DEEPSEEK_USAGE_TOKEN
usage_token: ""

# How often to check balance (seconds).  Minimum: 30.
poll_interval_seconds: 300

# How often to poll usage data (seconds).  Minimum: 600.  Default: 3600.
# Environment variable: DM_USAGE_POLL_INTERVAL
usage_poll_interval_seconds: 3600

# Balance thresholds for colour changes and desktop notifications.
#   above yellow — normal
#   yellow .. red — warning (🟡)
#   below red      — danger  (🔴)
alert_threshold_yellow: 5.0
alert_threshold_red: 1.0
YAMLEOF
    chmod 600 "$USER_CFG_DIR/config.yaml"
    echo "✓ User config created at $USER_CFG_DIR/config.yaml"
    echo ""
    read -rp "  → Enter your API key now (or press Enter to skip): " API_KEY
    if [ -n "$API_KEY" ]; then
        sed -i "s/sk-your-api-key-here/$API_KEY/" "$USER_CFG_DIR/config.yaml"
        echo "  ✓ API key saved."
    fi
else
    echo "⚠ User config already exists, skipping."
fi

# ---- 5. Data directory --------------------------------------------------------
mkdir -p "$DATA_DIR" "$DATA_DIR/logs" "$DATA_DIR/daily_summaries" "$DATA_DIR/panel"
echo "✓ Data directories ready: $DATA_DIR"

# ---- 6. Clean up old deepseek-monitor (v1.x) services --------------------------
echo ""
echo "→ Cleaning up old deepseek-monitor (v1.x) services …"
if systemctl --user is-active --quiet deepseek-monitor.service 2>/dev/null; then
    systemctl --user stop deepseek-monitor.service 2>/dev/null || true
    echo "  Stopped old deepseek-monitor.service."
fi
if systemctl --user is-enabled --quiet deepseek-monitor.service 2>/dev/null; then
    systemctl --user disable deepseek-monitor.service 2>/dev/null || true
    echo "  Disabled old deepseek-monitor.service."
fi
if systemctl --user is-active --quiet deepseek-monitor-report.timer 2>/dev/null; then
    systemctl --user stop deepseek-monitor-report.timer 2>/dev/null || true
    echo "  Stopped old deepseek-monitor-report.timer."
fi
if systemctl --user is-enabled --quiet deepseek-monitor-report.timer 2>/dev/null; then
    systemctl --user disable deepseek-monitor-report.timer 2>/dev/null || true
    echo "  Disabled old deepseek-monitor-report.timer."
fi
# Remove old unit files
for OLD in \
    "${HOME}/.config/systemd/user/deepseek-monitor.service" \
    "${HOME}/.config/systemd/user/deepseek-monitor-report.service" \
    "${HOME}/.config/systemd/user/deepseek-monitor-report.timer"; do
    if [ -f "$OLD" ]; then
        rm -f "$OLD"
        echo "  Removed $(basename "$OLD")."
    fi
done
# Remove old report service for panelwhale (deprecated in v2.0)
for OLD_RPT in \
    "${HOME}/.config/systemd/user/panelwhale-report.service" \
    "${HOME}/.config/systemd/user/panelwhale-report.timer"; do
    if [ -f "$OLD_RPT" ]; then
        systemctl --user stop "$(basename "$OLD_RPT")" 2>/dev/null || true
        systemctl --user disable "$(basename "$OLD_RPT")" 2>/dev/null || true
        rm -f "$OLD_RPT"
        echo "  Removed deprecated $(basename "$OLD_RPT")."
    fi
done
# Remove old application directory
if [ -d "/opt/deepseek-monitor" ]; then
    sudo rm -rf "/opt/deepseek-monitor"
    echo "✓ Old /opt/deepseek-monitor/ removed."
fi
echo "✓ Cleanup complete."

# ---- 7. Install systemd user service ------------------------------------------
echo ""
echo "→ Setting up systemd user services …"

SERVICE_DIR="${HOME}/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
cp "$APP_DIR/panelwhale.service" "$SERVICE_DIR/"

# Reload and enable
systemctl --user daemon-reload
systemctl --user enable panelwhale.service
echo "✓ Service enabled (autostart on login)."

# ---- 8. Start now -------------------------------------------------------------
echo ""
echo "→ Starting the monitor …"
# Stop any old instance first
systemctl --user stop panelwhale.service 2>/dev/null || true
pkill -f "python3.*deepseek.*main.py" 2>/dev/null || true
sleep 0.5

systemctl --user start panelwhale.service
sleep 1

if systemctl --user is-active --quiet panelwhale.service; then
    echo "✓ Monitor started."
    echo "  You should see the DeepSeek icon in your top panel."
else
    echo "⚠ Monitor may have failed to start. Check:"
    echo "  systemctl --user status panelwhale"
    echo "  journalctl --user -u panelwhale -n 20"
fi

# ---- 9. Done ------------------------------------------------------------------
echo ""
echo "========================================"
echo " Installation complete!"
echo ""
echo " Manage with:"
echo "   systemctl --user status panelwhale"
echo "   systemctl --user stop panelwhale"
echo "   systemctl --user start panelwhale"
echo "   journalctl --user -u panelwhale -f   (view logs)"
echo ""
echo " Control Panel: right-click the panel icon → Open Control Panel"
echo ""
echo " Files:"
echo "   Config:   $USER_CFG_DIR/config.yaml"
echo "   Data:     $DATA_DIR/logs/"
echo "   Service:  $SERVICE_DIR/panelwhale.service"
echo "========================================"
