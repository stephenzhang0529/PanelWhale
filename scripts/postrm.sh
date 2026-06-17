#!/usr/bin/env bash
#
# postrm.sh — Runs after PanelWhale .deb files are removed
#
# $1 = action: "remove" | "purge" | "upgrade" | "disappear"
#
set -euo pipefail

ACTION="${1:-remove}"

echo "========================================"
echo " PanelWhale — Post-remove"
echo "========================================"

# ---- Clean up systemd unit files ----------------------------------------
for _HOME in /home/*; do
    [ -d "$_HOME" ] || continue
    _USER=$(basename "$_HOME")
    rm -f "$_HOME/.config/systemd/user/panelwhale.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.service" \
          "$_HOME/.config/systemd/user/panelwhale-report.timer" \
          "$_HOME/.config/systemd/user/deepseek-monitor.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.service" \
          "$_HOME/.config/systemd/user/deepseek-monitor-report.timer"
    echo "  Removed unit files for user '$_USER'"
done

# ---- Handle config & data -----------------------------------------------
case "$ACTION" in
    purge)
        echo ""
        echo "→ Purging user config and data …"
        for _HOME in /home/*; do
            [ -d "$_HOME" ] || continue
            _USER=$(basename "$_HOME")
            _CFG="$_HOME/.config/panelwhale"
            _DATA="$_HOME/.local/share/panelwhale"
            if [ -d "$_CFG" ]; then
                rm -rf "$_CFG"
                echo "  Removed $_CFG"
            fi
            if [ -d "$_DATA" ]; then
                rm -rf "$_DATA"
                echo "  Removed $_DATA"
            fi
        done
        echo "✓ All config and data purged."
        ;;
    upgrade)
        # Keep everything during upgrade — nothing to do
        ;;
    *)
        # remove / disappear / failed-upgrade — keep config & data
        for _HOME in /home/*; do
            _CFG="$_HOME/.config/panelwhale"
            _DATA="$_HOME/.local/share/panelwhale"
            if [ -d "$_CFG" ] || [ -d "$_DATA" ]; then
                echo ""
                echo "  User data kept:"
                [ -d "$_CFG" ]  && echo "    $_CFG"
                [ -d "$_DATA" ] && echo "    $_DATA"
                echo ""
                echo "  To remove all traces, run: sudo apt purge panelwhale"
            fi
        done
        ;;
esac

echo "========================================"
echo " Done."
echo "========================================"
