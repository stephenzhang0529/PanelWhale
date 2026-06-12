import os
import time
import logging
import signal
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, GLib, Notify

# AppIndicator3 vs AyatanaAppIndicator3 (Ubuntu 20.04/22.04 vs 24.04+)
try:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as IndicatorModule
    _INDICATOR_CATEGORY = IndicatorModule.IndicatorCategory.APPLICATION_STATUS
except (ValueError, ImportError):
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as IndicatorModule
    _INDICATOR_CATEGORY = IndicatorModule.IndicatorCategory.APPLICATION_STATUS

from monitor.config import Config
from monitor.api import DeepSeekAPI, APIError, BalanceInfo
from monitor.store import BalanceStore

log = logging.getLogger(__name__)

# Try to locate the DeepSeek logo icon alongside the app.
# GTK handles downscaling automatically, so we use the original
# high-res image for crisp rendering on both regular and HiDPI panels.
_ICON_PATH = None
for _candidate in (
    os.path.join(os.path.dirname(__file__), "..", "deepseek-color.png"),
    "/opt/deepseek-monitor/deepseek-color.png",
):
    if os.path.isfile(_candidate):
        _ICON_PATH = _candidate
        break

LABEL_NORMAL = "\U0001f48e"    # 💎
LABEL_WARNING = "\U0001f7e1"   # 🟡
LABEL_DANGER = "\U0001f534"    # 🔴
LABEL_ERROR = "⚠️"              # ⚠️


class BalanceIndicator:
    def __init__(self, config: Config, api: DeepSeekAPI, store: BalanceStore):
        self._config = config
        self._api = api
        self._store = store
        self._alert_state: Optional[str] = None  # None | "yellow" | "red"
        self._shutting_down = False
        self._last_manual_refresh: float = 0.0  # debounce timestamp

        Notify.init("deepseek-monitor")

        # ---- Build indicator ----
        self._indicator = IndicatorModule.Indicator.new(
            "deepseek-monitor",
            "utilities-system-monitor",
            _INDICATOR_CATEGORY,
        )
        self._indicator.set_status(IndicatorModule.IndicatorStatus.ACTIVE)

        # Use DeepSeek logo icon if available
        if _ICON_PATH:
            self._indicator.set_icon_full(_ICON_PATH, "DeepSeek")
            log.debug("Using icon: %s", _ICON_PATH)

        # ---- Build menu ----
        self._menu = Gtk.Menu()
        self._build_menu()
        self._indicator.set_menu(self._menu)
        self._menu.show_all()

        self._set_label(LABEL_ERROR + " 加载中...")

        # ---- Shutdown hooks ----
        self._install_shutdown_handlers()

        # ---- Start polling ----
        self._do_poll()
        GLib.timeout_add_seconds(config.poll_interval_seconds, self._on_timer)

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        self._menuitem_total = self._add_info_item("总余额: ---")
        self._menuitem_granted = self._add_info_item("  充值余额: ---")
        self._menuitem_topped = self._add_info_item("  赠送余额: ---")
        self._add_separator()

        self._menuitem_5m = self._add_info_item("过去5分钟:  ---")
        self._menuitem_30m = self._add_info_item("过去30分钟: ---")
        self._menuitem_3h = self._add_info_item("过去3小时:  ---")
        self._menuitem_today = self._add_info_item("今日累计:   ---")
        self._add_separator()

        self._menuitem_updated = self._add_info_item("上次更新: ---")
        self._add_separator()

        refresh_item = Gtk.MenuItem(label="🔄 立即刷新")
        refresh_item.connect("activate", self._on_manual_refresh)
        self._menu.append(refresh_item)
        self._add_separator()

        quit_item = Gtk.MenuItem(label="❌ 退出")
        quit_item.connect("activate", self._on_quit)
        self._menu.append(quit_item)

    def _add_info_item(self, label: str) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.set_sensitive(False)
        self._menu.append(item)
        return item

    def _add_separator(self) -> None:
        self._menu.append(Gtk.SeparatorMenuItem())

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _install_shutdown_handlers(self) -> None:
        """Catch SIGTERM / SIGINT so we can flush the session log before exit."""
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                             self._on_shutdown_signal, None)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT,
                             self._on_shutdown_signal, None)

    def _on_shutdown_signal(self, _user_data) -> bool:
        log.info("Shutdown signal received – flushing session log …")
        self._shutdown_gracefully()
        Gtk.main_quit()
        return False  # don't keep the handler

    def _on_quit(self, _widget) -> None:
        log.info("Quit from menu – flushing session log …")
        self._shutdown_gracefully()
        Gtk.main_quit()

    def _shutdown_gracefully(self) -> None:
        """Final API poll + end_session, best-effort.

        Even if the final poll fails (e.g. network already down), we still
        flush the accumulated session data so today's total survives a reboot.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            balance = self._api.get_balance()
            self._store.end_session(balance)
        except APIError as e:
            log.warning("Final poll failed during shutdown: %s", e)
            self._store.flush()  # preserve what we have
        try:
            Notify.uninit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Polling & UI update
    # ------------------------------------------------------------------

    def _on_timer(self) -> bool:
        if not self._shutting_down:
            self._do_poll()
        return True

    def _on_manual_refresh(self, _widget) -> None:
        """Handle the '🔄 立即刷新' menu item with 15-second debounce."""
        now = time.time()
        if now - self._last_manual_refresh < 15:
            log.debug("Manual refresh skipped — within debounce window")
            return
        self._last_manual_refresh = now
        self._do_poll()

    def _do_poll(self) -> None:
        try:
            balance = self._api.get_balance()
        except APIError as e:
            log.warning("API poll failed: %s", e)
            self._set_label(LABEL_ERROR + " 无连接")
            self._menuitem_updated.set_label("上次更新: 失败")
            return

        self._store.add(balance)
        self._update_ui(balance)

    def _update_ui(self, balance: BalanceInfo) -> None:
        total = balance.total_balance
        sym = balance.symbol

        # -- Label --
        self._set_balance_label(total, sym)

        # -- Balance detail --
        self._menuitem_total.set_label(f"总余额: {sym}{total:.2f}")
        self._menuitem_topped.set_label(
            f"  充值余额: {sym}{balance.topped_up_balance:.2f}"
        )
        self._menuitem_granted.set_label(
            f"  赠送余额: {sym}{balance.granted_balance:.2f}"
        )

        # -- Consumption (best-effort from current session) --
        self._menuitem_5m.set_label(
            self._fmt_consumption("过去5分钟", self._store.consumption_since(5), sym)
        )
        self._menuitem_30m.set_label(
            self._fmt_consumption("过去30分钟", self._store.consumption_since(30), sym)
        )
        self._menuitem_3h.set_label(
            self._fmt_consumption("过去3小时", self._store.consumption_since(180), sym)
        )

        # -- Today = logs from previous sessions + current session --
        today_total = self._store.today_consumption()
        self._menuitem_today.set_label(f"今日累计:   {sym}{today_total:.2f}")

        # -- Update time --
        self._menuitem_updated.set_label(
            f"上次更新: {self._store.latest_update_time()}"
        )

        # -- Alert --
        self._check_alert(total, sym)

    # ------------------------------------------------------------------
    # Label helpers
    # ------------------------------------------------------------------

    def _set_balance_label(self, total: float, sym: str) -> None:
        if total > self._config.alert_threshold_yellow:
            emoji = LABEL_NORMAL
        elif total > self._config.alert_threshold_red:
            emoji = LABEL_WARNING
        else:
            emoji = LABEL_DANGER
        self._set_label(f"{emoji} {sym}{total:.2f}")

    def _set_label(self, text: str) -> None:
        self._indicator.set_label(text, "")

    @staticmethod
    def _fmt_consumption(prefix: str, value: Optional[float], sym: str) -> str:
        if value is None:
            return f"{prefix}:  ---"
        return f"{prefix}: {sym}{value:.2f}"

    # ------------------------------------------------------------------
    # Desktop notifications
    # ------------------------------------------------------------------

    def _check_alert(self, total: float, sym: str) -> None:
        if total <= self._config.alert_threshold_red:
            new_state = "red"
            if self._alert_state != "red":
                self._notify(
                    "⚠️ 余额严重不足！",
                    f"DeepSeek 余额仅剩 {sym}{total:.2f}，请立即充值。",
                    urgency=2,
                )
        elif total <= self._config.alert_threshold_yellow:
            new_state = "yellow"
            if self._alert_state not in ("yellow", "red"):
                self._notify(
                    "余额不足提醒",
                    f"DeepSeek 余额剩余 {sym}{total:.2f}，建议尽快充值。",
                    urgency=1,
                )
        else:
            new_state = None
        self._alert_state = new_state

    @staticmethod
    def _notify(summary: str, body: str, urgency: int = 1) -> None:
        notification = Notify.Notification.new(summary, body)
        notification.set_urgency(urgency)
        try:
            notification.show()
        except Exception:
            log.warning("Failed to show notification", exc_info=True)
