"""Settings window for PanelWhale.

Provides a GTK 3 form to edit API keys, polling intervals, alert thresholds,
and autostart.  On save the credentials are verified against the live API
and the result is shown inline.
"""

import os
import subprocess
import logging
from typing import Optional, Callable

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from monitor.config import Config, save_config, get_data_root
from monitor.api import DeepSeekAPI, APIError, BalanceInfo
from monitor.usage_api import UsageAPI, UsageAPIError, MonthlyUsage

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Dropdown mappings
# ------------------------------------------------------------------

BALANCE_INTERVALS = [
    ("30 seconds", 30),
    ("1 minute", 60),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("30 minutes", 1800),
    ("1 hour", 3600),
]

USAGE_INTERVALS = [
    ("10 minutes", 600),
    ("30 minutes", 1800),
    ("1 hour", 3600),
    ("2 hours", 7200),
    ("6 hours", 21600),
]


def _find_combo_index(intervals: list, seconds: int) -> int:
    """Return the index of *seconds* in *intervals*, defaulting to 0."""
    for i, (_label, val) in enumerate(intervals):
        if val == seconds:
            return i
    return 0


# ------------------------------------------------------------------
# SettingsWindow
# ------------------------------------------------------------------


class SettingsWindow(Gtk.Window):
    """GTK window for editing PanelWhale settings.

    Parameters:
        current_config: The live ``Config`` to populate the form.
        api: A ``DeepSeekAPI`` instance for the current key (may be used
            for verification).
        usage_api: A ``UsageAPI`` instance (or ``None``).
        on_saved: Called as ``on_saved(new_config)`` after a successful
            save so the indicator can reload.
    """

    def __init__(
        self,
        current_config: Config,
        api: DeepSeekAPI,
        usage_api,
        on_saved: Callable[[Config], None],
    ):
        super().__init__(title="PanelWhale Settings")
        self._config = current_config
        self._api = api
        self._usage_api = usage_api
        self._on_saved = on_saved

        self.set_default_size(520, -1)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_border_width(16)
        self.add(vbox)

        # Build form sections
        self._build_api_key_section(vbox)
        self._build_usage_token_section(vbox)
        self._build_polling_section(vbox)
        self._build_thresholds_section(vbox)
        self._build_autostart_section(vbox)
        self._build_status_section(vbox)
        self._build_buttons(vbox)

        self.show_all()

    # ------------------------------------------------------------------
    # API Key
    # ------------------------------------------------------------------

    def _build_api_key_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("API Key")
        parent.pack_start(frame, False, False, 0)

        row = Gtk.Box(spacing=6)
        frame.add(row)

        self._api_entry = Gtk.Entry()
        self._api_entry.set_visibility(False)
        self._api_entry.set_text(self._config.api_key)
        self._api_entry.set_placeholder_text("sk-your-api-key-here")
        row.pack_start(self._api_entry, True, True, 0)

        self._api_eye = Gtk.Button(label="👁")
        self._api_eye.set_tooltip_text("Show / hide API key")
        self._api_eye.connect("clicked", self._on_toggle_api_visibility)
        row.pack_start(self._api_eye, False, False, 0)

    def _on_toggle_api_visibility(self, _btn) -> None:
        visible = not self._api_entry.get_visibility()
        self._api_entry.set_visibility(visible)
        self._api_eye.set_label("🙈" if visible else "👁")

    # ------------------------------------------------------------------
    # Usage Token
    # ------------------------------------------------------------------

    def _build_usage_token_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("Usage Token")
        parent.pack_start(frame, False, False, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        frame.add(vbox)

        row = Gtk.Box(spacing=6)
        vbox.pack_start(row, True, True, 0)

        self._token_entry = Gtk.Entry()
        self._token_entry.set_visibility(False)
        self._token_entry.set_text(self._config.usage_token)
        self._token_entry.set_placeholder_text("Paste token from browser console")
        row.pack_start(self._token_entry, True, True, 0)

        self._token_eye = Gtk.Button(label="👁")
        self._token_eye.set_tooltip_text("Show / hide usage token")
        self._token_eye.connect("clicked", self._on_toggle_token_visibility)
        row.pack_start(self._token_eye, False, False, 0)

        hint = Gtk.Label()
        hint.set_markup(
            '<span size="small" foreground="#888">'
            "💡 Browser console: <tt>JSON.parse(localStorage.userToken).value</tt>"
            "</span>"
        )
        hint.set_halign(Gtk.Align.START)
        vbox.pack_start(hint, False, False, 0)

    def _on_toggle_token_visibility(self, _btn) -> None:
        visible = not self._token_entry.get_visibility()
        self._token_entry.set_visibility(visible)
        self._token_eye.set_label("🙈" if visible else "👁")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _build_polling_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("Polling")
        parent.pack_start(frame, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(6)
        frame.add(grid)

        # Balance interval
        lbl_bal = Gtk.Label(label="Balance check:")
        lbl_bal.set_halign(Gtk.Align.END)
        grid.attach(lbl_bal, 0, 0, 1, 1)

        self._balance_combo = Gtk.ComboBoxText()
        for label, _val in BALANCE_INTERVALS:
            self._balance_combo.append_text(label)
        idx = _find_combo_index(
            BALANCE_INTERVALS, self._config.poll_interval_seconds
        )
        self._balance_combo.set_active(idx)
        grid.attach(self._balance_combo, 1, 0, 1, 1)

        # Usage interval
        lbl_use = Gtk.Label(label="Usage check:")
        lbl_use.set_halign(Gtk.Align.END)
        grid.attach(lbl_use, 0, 1, 1, 1)

        self._usage_combo = Gtk.ComboBoxText()
        for label, _val in USAGE_INTERVALS:
            self._usage_combo.append_text(label)
        idx = _find_combo_index(
            USAGE_INTERVALS, self._config.usage_poll_interval_seconds
        )
        self._usage_combo.set_active(idx)
        grid.attach(self._usage_combo, 1, 1, 1, 1)

    # ------------------------------------------------------------------
    # Alert Thresholds
    # ------------------------------------------------------------------

    def _build_thresholds_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("Alert Thresholds")
        parent.pack_start(frame, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(6)
        frame.add(grid)

        lbl_y = Gtk.Label(label="Warning (🟡):")
        lbl_y.set_halign(Gtk.Align.END)
        grid.attach(lbl_y, 0, 0, 1, 1)

        self._yellow_entry = Gtk.Entry()
        self._yellow_entry.set_text(str(self._config.alert_threshold_yellow))
        self._yellow_entry.set_width_chars(6)
        grid.attach(self._yellow_entry, 1, 0, 1, 1)

        lbl_r = Gtk.Label(label="Critical (🔴):")
        lbl_r.set_halign(Gtk.Align.END)
        grid.attach(lbl_r, 2, 0, 1, 1)

        self._red_entry = Gtk.Entry()
        self._red_entry.set_text(str(self._config.alert_threshold_red))
        self._red_entry.set_width_chars(6)
        grid.attach(self._red_entry, 3, 0, 1, 1)

    # ------------------------------------------------------------------
    # Autostart
    # ------------------------------------------------------------------

    def _build_autostart_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("Autostart")
        parent.pack_start(frame, False, False, 0)

        self._autostart_check = Gtk.CheckButton(
            label="Start PanelWhale on login"
        )
        enabled = self._autostart_is_enabled()
        self._autostart_check.set_active(enabled)
        if not self._systemctl_available():
            self._autostart_check.set_sensitive(False)
            self._autostart_check.set_tooltip_text(
                "systemctl not available — cannot manage autostart"
            )
        frame.add(self._autostart_check)

    @staticmethod
    def _systemctl_available() -> bool:
        try:
            subprocess.run(
                ["which", "systemctl"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def _autostart_is_enabled() -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "panelwhale.service"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _build_status_section(self, parent: Gtk.Box) -> None:
        frame = self._section_frame("Status")
        parent.pack_start(frame, False, False, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        frame.add(vbox)

        self._status_balance = Gtk.Label(label="Balance: —")
        self._status_balance.set_halign(Gtk.Align.START)
        vbox.pack_start(self._status_balance, False, False, 0)

        self._status_usage = Gtk.Label(label="Usage: —")
        self._status_usage.set_halign(Gtk.Align.START)
        vbox.pack_start(self._status_usage, False, False, 0)

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _build_buttons(self, parent: Gtk.Box) -> None:
        bbox = Gtk.Box(spacing=8)
        bbox.set_halign(Gtk.Align.END)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        bbox.pack_start(cancel, False, False, 0)

        self._save_btn = Gtk.Button(label="💾  Save")
        self._save_btn.get_style_context().add_class("suggested-action")
        self._save_btn.connect("clicked", self._on_save)
        bbox.pack_start(self._save_btn, False, False, 0)

        parent.pack_start(bbox, False, False, 0)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_cancel(self, _btn) -> None:
        self.destroy()

    def _on_save(self, _btn) -> None:
        # Build new config from widgets
        new_config = self._collect_config()

        # Validate thresholds
        if new_config.alert_threshold_yellow <= new_config.alert_threshold_red:
            self._status_balance.set_markup(
                '<span foreground="red">❌ Yellow threshold must be greater than red</span>'
            )
            return

        # Save to disk
        try:
            path = save_config(new_config)
            log.info("Config saved to %s", path)
        except OSError as e:
            self._status_balance.set_markup(
                f'<span foreground="red">❌ Failed to save: {e}</span>'
            )
            return

        # Handle autostart change
        self._apply_autostart()

        # Verify credentials against live API
        self._verify_and_update_status(new_config)

        # Notify indicator
        self._on_saved(new_config)

    def _collect_config(self) -> Config:
        """Read all widget values into a new ``Config``."""
        bal_idx = self._balance_combo.get_active()
        bal_sec = BALANCE_INTERVALS[bal_idx][1] if bal_idx >= 0 else 300

        use_idx = self._usage_combo.get_active()
        use_sec = USAGE_INTERVALS[use_idx][1] if use_idx >= 0 else 3600

        try:
            yellow = float(self._yellow_entry.get_text())
        except ValueError:
            yellow = self._config.alert_threshold_yellow

        try:
            red = float(self._red_entry.get_text())
        except ValueError:
            red = self._config.alert_threshold_red

        return Config(
            api_key=self._api_entry.get_text().strip(),
            usage_token=self._token_entry.get_text().strip(),
            poll_interval_seconds=bal_sec,
            usage_poll_interval_seconds=use_sec,
            alert_threshold_yellow=yellow,
            alert_threshold_red=red,
        )

    def _apply_autostart(self) -> None:
        """Enable or disable the systemd user service based on the checkbox."""
        want_enable = self._autostart_check.get_active()
        action = "enable" if want_enable else "disable"
        try:
            subprocess.run(
                ["systemctl", "--user", action, "panelwhale.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            log.info("Autostart %sd", action)
        except Exception as e:
            log.warning("Failed to %s autostart: %s", action, e)

    def _verify_and_update_status(self, cfg: Config) -> None:
        """Hit the APIs with the new credentials and update status labels."""
        # Balance verification
        if cfg.api_key:
            try:
                temp_api = DeepSeekAPI(cfg.api_key)
                balance = temp_api.get_balance()
                sym = balance.symbol
                self._status_balance.set_markup(
                    f'<span foreground="#1a73e8">✅ Balance: {sym}{balance.total_balance:.2f}</span>'
                )
            except APIError as e:
                self._status_balance.set_markup(
                    f'<span foreground="red">❌ Balance API: {e}</span>'
                )
        else:
            self._status_balance.set_markup(
                '<span foreground="#888">⚠ No API key configured</span>'
            )

        # Usage verification
        if cfg.usage_token:
            try:
                from datetime import datetime
                from monitor.usage_cache import save_usage as cache_save
                temp_usage = UsageAPI(cfg.usage_token)
                now = datetime.now()
                monthly = temp_usage.get_monthly_usage(now.month, now.year)
                cache_save(monthly)
                total_hit = sum(
                    m.cache_hit_tokens for m in monthly.models.values()
                )
                total_miss = sum(
                    m.cache_miss_tokens for m in monthly.models.values()
                )
                denom = total_hit + total_miss
                hit_pct = round((total_hit / denom * 100) if denom > 0 else 0, 1)
                sym = _currency_symbol()
                self._status_usage.set_markup(
                    f'<span foreground="#00897b">✅ Usage: {sym}{monthly.total_cost:.2f} '
                    f"MTD ({hit_pct}% cache hit)</span>"
                )
            except UsageAPIError as e:
                self._status_usage.set_markup(
                    f'<span foreground="red">❌ Usage API: {e}</span>'
                )
        else:
            self._status_usage.set_markup(
                '<span foreground="#888">⚠ No usage token configured</span>'
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _section_frame(title: str) -> Gtk.Frame:
        """Create a labelled frame with a bold label."""
        frame = Gtk.Frame()
        label = Gtk.Label()
        label.set_markup(f"<b>{title}</b>")
        frame.set_label_widget(label)
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        return frame


def _currency_symbol() -> str:
    """Read cached currency code, return symbol. Defaults to ¥."""
    import json
    cache = os.path.join(get_data_root(), "currency")
    mapping = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
    try:
        with open(cache, "r") as f:
            code = f.read().strip()
        return mapping.get(code, code)
    except FileNotFoundError:
        return "¥"
