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
from monitor.panel import generate_control_panel

log = logging.getLogger(__name__)

# Try to locate the DeepSeek logo icon alongside the app.
# GTK handles downscaling automatically, so we use the original
# high-res image for crisp rendering on both regular and HiDPI panels.
_ICON_PATH = None
for _candidate in (
    os.path.join(os.path.dirname(__file__), "deepseek-color.png"),
    "/opt/panelwhale/monitor/deepseek-color.png",
):
    if os.path.isfile(_candidate):
        _ICON_PATH = _candidate
        break

LABEL_NORMAL = ""               # > ¥5 — no emoji needed
LABEL_WARNING = "\U0001f7e1"   # 🟡
LABEL_DANGER = "\U0001f534"    # 🔴
LABEL_ERROR = "⚠️"              # ⚠️


class BalanceIndicator:
    def __init__(self, config: Config, api: DeepSeekAPI, store: BalanceStore,
                 usage_api=None):
        self._config = config
        self._api = api
        self._store = store
        self._usage_api = usage_api
        self._alert_state: Optional[str] = None  # None | "yellow" | "red"
        self._shutting_down = False
        self._last_manual_refresh: float = 0.0  # debounce timestamp
        self._settings_window = None  # track the settings Gtk.Window
        self._balance_timer_id: int = 0
        self._usage_timer_id: int = 0

        Notify.init("panelwhale")

        # ---- Build indicator ----
        self._indicator = IndicatorModule.Indicator.new(
            "panelwhale",
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
        self._charge_item.hide()  # hidden until balance drops ≤ yellow threshold
        self._menu.show_all()

        self._set_label(LABEL_ERROR + " Loading...")

        # ---- Shutdown hooks ----
        self._install_shutdown_handlers()

        # ---- Start polling ----
        self._do_poll()
        self._balance_timer_id = GLib.timeout_add_seconds(
            config.poll_interval_seconds, self._on_timer
        )

        # ---- Start usage polling (if token available) ----
        if self._usage_api is not None:
            self._do_usage_poll()
            self._usage_timer_id = GLib.timeout_add_seconds(
                config.usage_poll_interval_seconds, self._on_usage_timer
            )

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        self._menuitem_total = self._add_info_item("Total Balance: ---")
        self._menuitem_topped = self._add_info_item("  Topped-up: ---")
        self._menuitem_granted = self._add_info_item("  Granted: ---")
        self._add_separator()

        self._menuitem_5m = self._add_info_item("Last 5 min:  ---")
        self._menuitem_30m = self._add_info_item("Last 30 min: ---")
        self._menuitem_3h = self._add_info_item("Last 3 hr:   ---")
        self._menuitem_today = self._add_info_item("Today:       ---")
        self._add_separator()

        # ── Usage This Month section (hidden when no usage token) ──
        self._menuitem_usage_header = self._add_info_item("Usage This Month")
        self._menuitem_usage_total = self._add_info_item("  Total Cost: ---")
        self._menuitem_usage_flash = self._add_info_item("  Flash: ---")
        self._menuitem_usage_pro = self._add_info_item("  Pro: ---")
        if self._usage_api is None:
            self._menuitem_usage_header.hide()
            self._menuitem_usage_total.hide()
            self._menuitem_usage_flash.hide()
            self._menuitem_usage_pro.hide()
        self._add_separator()
        # ── End usage section ──

        self._menuitem_updated = self._add_info_item("Last update: ---")
        self._add_separator()

        # Charge button — only visible when balance is low
        self._charge_item = Gtk.MenuItem(label="Charge")
        self._charge_item.connect("activate", self._on_charge)
        self._menu.append(self._charge_item)
        self._add_separator()

        refresh_item = Gtk.MenuItem(label="Refresh")
        refresh_item.connect("activate", self._on_manual_refresh)
        self._menu.append(refresh_item)

        settings_item = Gtk.MenuItem(label="Settings")
        settings_item.connect("activate", self._on_settings)
        self._menu.append(settings_item)
        self._add_separator()

        report_item = Gtk.MenuItem(label="Open Control Panel")
        report_item.connect("activate", self._on_open_panel)
        self._menu.append(report_item)
        self._add_separator()

        quit_item = Gtk.MenuItem(label="Quit")
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

    def _on_charge(self, _widget) -> None:
        """Open the DeepSeek top-up page in the default browser."""
        import subprocess
        url = "https://platform.deepseek.com/top_up"
        # Same browser-finding logic as _on_open_report
        for browser in (
            "sensible-browser", "x-www-browser",
            "firefox", "google-chrome", "chromium-browser", "chromium",
        ):
            if subprocess.run(["which", browser],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                subprocess.Popen([browser, url], start_new_session=True)
                return
        subprocess.Popen(["xdg-open", url], start_new_session=True)

    def _on_manual_refresh(self, _widget) -> None:
        """Handle the 'Refresh' menu item with 15-second debounce."""
        now = time.time()
        if now - self._last_manual_refresh < 15:
            log.debug("Manual refresh skipped — within debounce window")
            return
        self._last_manual_refresh = now
        self._do_poll()
        if self._usage_api is not None:
            self._do_usage_poll()

    def _on_settings(self, _widget) -> None:
        """Open the Settings window (one at a time)."""
        from monitor.settings import SettingsWindow

        # If a settings window is already open, just present it
        if self._settings_window is not None:
            self._settings_window.present()
            return

        self._settings_window = SettingsWindow(
            self._config,
            self._api,
            self._usage_api,
            on_saved=self._on_settings_saved,
        )
        self._settings_window.connect("destroy", self._on_settings_destroyed)

    def _on_settings_destroyed(self, _window) -> None:
        """Clear the reference when the settings window is closed."""
        self._settings_window = None

    def _on_settings_saved(self, new_config: Config) -> None:
        """Handle config changes after the user saves settings.

        Recreates API objects and restarts timers for any fields that changed.
        """
        api_key_changed = new_config.api_key != self._config.api_key
        token_changed = new_config.usage_token != self._config.usage_token
        balance_interval_changed = (
            new_config.poll_interval_seconds != self._config.poll_interval_seconds
        )
        usage_interval_changed = (
            new_config.usage_poll_interval_seconds
            != self._config.usage_poll_interval_seconds
        )

        # Update the in-memory config
        self._config = new_config

        # Recreate balance API if key changed
        if api_key_changed:
            self._api = DeepSeekAPI(new_config.api_key)

        # Recreate or clear usage API if token changed
        if token_changed:
            if new_config.usage_token:
                from monitor.usage_api import UsageAPI
                self._usage_api = UsageAPI(new_config.usage_token)
                self._menuitem_usage_header.show()
                self._menuitem_usage_total.show()
                self._menuitem_usage_flash.show()
                self._menuitem_usage_pro.show()
                # Start usage timer if not already running
                if self._usage_timer_id == 0:
                    self._do_usage_poll()
                    self._usage_timer_id = GLib.timeout_add_seconds(
                        new_config.usage_poll_interval_seconds,
                        self._on_usage_timer,
                    )
            else:
                self._usage_api = None
                self._menuitem_usage_header.hide()
                self._menuitem_usage_total.hide()
                self._menuitem_usage_flash.hide()
                self._menuitem_usage_pro.hide()
                if self._usage_timer_id:
                    GLib.source_remove(self._usage_timer_id)
                    self._usage_timer_id = 0

        # Restart balance timer if interval changed
        if balance_interval_changed and self._balance_timer_id:
            GLib.source_remove(self._balance_timer_id)
            self._balance_timer_id = GLib.timeout_add_seconds(
                new_config.poll_interval_seconds, self._on_timer
            )

        # Restart usage timer if interval changed
        if (
            usage_interval_changed
            and self._usage_timer_id
            and self._usage_api is not None
        ):
            GLib.source_remove(self._usage_timer_id)
            self._usage_timer_id = GLib.timeout_add_seconds(
                new_config.usage_poll_interval_seconds, self._on_usage_timer
            )

        # Do an immediate poll with the new credentials
        self._do_poll()
        if self._usage_api is not None:
            self._do_usage_poll()

    def _on_open_panel(self, _widget) -> None:
        """Generate and open the control panel in the default browser."""
        import subprocess
        import logging
        log = logging.getLogger(__name__)
        try:
            path = generate_control_panel(
                self._config, self._api, self._usage_api, self._store
            )
        except Exception:
            log.exception("Failed to generate control panel")
            self._notify(
                "Panel Error",
                "Failed to generate control panel. Check the logs for details.",
                urgency=2,
            )
            return
        # Try browsers explicitly — xdg-open may honor a misconfigured
        # .html file association (e.g. Clash Party instead of a browser).
        for browser in (
            "sensible-browser",
            "x-www-browser",
            "firefox",
            "google-chrome",
            "chromium-browser",
            "chromium",
        ):
            if subprocess.run(["which", browser],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                subprocess.Popen([browser, path], start_new_session=True)
                return
        # Last resort
        subprocess.Popen(["xdg-open", path], start_new_session=True)

    def _do_poll(self) -> None:
        try:
            balance = self._api.get_balance()
        except APIError as e:
            log.warning("API poll failed: %s", e)
            self._set_label(LABEL_ERROR + " No Connection")
            self._menuitem_updated.set_label("Last update: Failed")
            return

        self._store.add(balance)
        self._update_ui(balance)

    # ------------------------------------------------------------------
    # Usage polling
    # ------------------------------------------------------------------

    def _on_usage_timer(self) -> bool:
        """GLib timer callback for usage polling."""
        if not self._shutting_down and self._usage_api is not None:
            self._do_usage_poll()
        return True

    def _do_usage_poll(self) -> None:
        """Fetch monthly usage and update the menu section."""
        from datetime import datetime
        from monitor.usage_api import UsageAPIError
        from monitor.usage_cache import save_usage, load_usage

        try:
            now = datetime.now()
            usage = self._usage_api.get_monthly_usage(now.month, now.year)
            save_usage(usage)
            self._update_usage_menu(usage)
            log.debug("Usage poll succeeded — MTD cost: ¥%.2f", usage.total_cost)
        except UsageAPIError as e:
            log.warning("Usage poll failed: %s", e)
            # Fall back to cached data
            cached = load_usage()
            if cached:
                self._update_usage_menu(cached)
                log.debug("Using cached usage data (%.1fh old)",
                          getattr(cached, '_age', 0))

    def _update_usage_menu(self, usage) -> None:
        """Refresh the Usage This Month menu items from a MonthlyUsage."""
        from monitor.store import _load_currency_symbol
        sym = _load_currency_symbol()

        self._menuitem_usage_total.set_label(
            f"  Total Cost: {sym}{usage.total_cost:.2f}"
        )

        for attr, key in [("_menuitem_usage_flash", "flash"),
                           ("_menuitem_usage_pro", "pro")]:
            item = getattr(self, attr)
            m = usage.models.get(key)
            if m:
                tokens_k = m.total_tokens / 1000
                hit_pct = m.cache_hit_rate * 100
                item.set_label(
                    f"  {m.display_name}: {tokens_k:.0f}K tokens "
                    f"({hit_pct:.0f}% cache hit) - {sym}{m.total_cost:.2f}"
                )
            else:
                name = key.title()
                item.set_label(f"  {name}: no data")

    def _update_ui(self, balance: BalanceInfo) -> None:
        total = balance.total_balance
        sym = balance.symbol

        # -- Label --
        self._set_balance_label(total, sym)

        # -- Balance detail --
        self._menuitem_total.set_label(f"Total Balance: {sym}{total:.2f}")
        self._menuitem_topped.set_label(
            f"  Topped-up: {sym}{balance.topped_up_balance:.2f}"
        )
        self._menuitem_granted.set_label(
            f"  Granted: {sym}{balance.granted_balance:.2f}"
        )

        # -- Consumption (best-effort from current session) --
        self._menuitem_5m.set_label(
            self._fmt_consumption("Last 5 min", self._store.consumption_since(5), sym)
        )
        self._menuitem_30m.set_label(
            self._fmt_consumption("Last 30 min", self._store.consumption_since(30), sym)
        )
        self._menuitem_3h.set_label(
            self._fmt_consumption("Last 3 hr", self._store.consumption_since(180), sym)
        )

        # -- Today = logs from previous sessions + current session --
        today_total = self._store.today_consumption()
        self._menuitem_today.set_label(f"Today:       {sym}{today_total:.2f}")

        # -- Update time --
        self._menuitem_updated.set_label(
            f"Last update: {self._store.latest_update_time()}"
        )

        # -- Alert --
        self._check_alert(total, sym)

        # -- Charge button (visible only when balance is low) --
        if total <= self._config.alert_threshold_yellow:
            self._charge_item.show()
        else:
            self._charge_item.hide()

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
        prefix = f"{emoji} " if emoji else ""
        self._set_label(f"{prefix}{sym}{total:.2f}")

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
                    "Balance Critical",
                    f"Only {sym}{total:.2f} remaining. Top up immediately.",
                    urgency=2,
                )
        elif total <= self._config.alert_threshold_yellow:
            new_state = "yellow"
            if self._alert_state not in ("yellow", "red"):
                self._notify(
                    "Balance Low",
                    f"{sym}{total:.2f} remaining. Consider topping up soon.",
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
