"""Windows system-tray indicator for PanelWhale.

Displays DeepSeek API balance as text in the Windows taskbar notification
area (like 鲁大师).  Uses pystray + Pillow to dynamically render balance
numbers as tray icons and provides a right-click context menu.

Left-click  → Open control panel in browser
Right-click → Context menu (balance details, refresh, charge, settings, quit)
"""

import os
import sys
import time
import logging
import threading
import webbrowser
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import pystray

from monitor.config import Config, get_data_root, get_config_dir, save_config
from monitor.api import DeepSeekAPI, APIError, BalanceInfo
from monitor.store import BalanceStore

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Icon rendering
# ------------------------------------------------------------------

ICON_SIZE = 128

# State colours (green / amber / red / grey)
_COLORS = {
    "normal": (76, 175, 80),
    "warning": (255, 193, 7),
    "danger": (220, 53, 69),
    "loading": (108, 117, 125),
}

# Try to load a CJK-capable font so ¥ / CNY renders correctly
_FONT = None
_FONT_SMALL = None


def _init_fonts() -> None:
    global _FONT, _FONT_SMALL

    # Build a list of (full_path, size_offset) pairs so that CJK fonts
    # which tend to have thinner glyphs get a slight size boost.
    font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    candidates: list[tuple[str, int]] = [
        (os.path.join(font_dir, "msyh.ttc"), 2),   # Microsoft YaHei (CJK)
        (os.path.join(font_dir, "msyhbd.ttc"), 0),  # Microsoft YaHei Bold
        (os.path.join(font_dir, "simhei.ttf"), 2),  # SimHei (CJK)
        (os.path.join(font_dir, "arial.ttf"), 0),   # Arial
        (os.path.join(font_dir, "segoeui.ttf"), 0), # Segoe UI
        (os.path.join(font_dir, "calibri.ttf"), 0), # Calibri
    ]

    for path, offset in candidates:
        if not os.path.isfile(path):
            continue
        try:
            _FONT = ImageFont.truetype(path, 56 + offset)
            _FONT_SMALL = ImageFont.truetype(path, 38 + offset)
            log.debug("Using font: %s", path)
            return
        except Exception:
            continue

    # Last resort: default bitmap font (limited glyph coverage)
    try:
        _FONT = ImageFont.load_default()
    except Exception:
        _FONT = None
    _FONT_SMALL = _FONT


_init_fonts()


def _make_icon(text: str, state: str = "normal") -> Image.Image:
    """Render *text* onto a coloured circle and return a 128×128 RGBA image."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg = _COLORS.get(state, _COLORS["normal"])
    margin = 2
    draw.ellipse([margin, margin, ICON_SIZE - margin, ICON_SIZE - margin], fill=bg)

    font = (_FONT if len(text) <= 7 else _FONT_SMALL) if _FONT is not None else None
    if font is not None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (ICON_SIZE - tw) // 2
        y = (ICON_SIZE - th) // 2 - 4
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
    else:
        # Bare-minimum fallback — draw a small white rectangle as placeholder
        s = 20
        draw.rectangle(
            [(ICON_SIZE - s) // 2, (ICON_SIZE - s) // 2,
             (ICON_SIZE + s) // 2, (ICON_SIZE + s) // 2],
            fill=(255, 255, 255),
        )

    return img


# ------------------------------------------------------------------
# Tray indicator
# ------------------------------------------------------------------


class WindowsTrayIndicator:
    """Windows system-tray balance indicator.

    Shows DeepSeek balance as a coloured icon in the notification area,
    with a right-click menu for details and actions.  Left-click opens
    the HTML control panel in the default browser.
    """

    def __init__(
        self,
        config: Config,
        api: DeepSeekAPI,
        store: BalanceStore,
        usage_api=None,
    ):
        self._config = config
        self._api = api
        self._store = store
        self._usage_api = usage_api
        self._alert_state: Optional[str] = None
        self._shutting_down = False
        self._last_manual_refresh: float = 0.0
        self._last_balance: Optional[BalanceInfo] = None

        # ---- Build tray icon ----
        self._tray = pystray.Icon(
            "panelwhale",
            _make_icon("...", "loading"),
            "PanelWhale — DeepSeek Balance Monitor",
            menu=self._make_menu(),
        )

        # ---- Start timers ----
        self._balance_timer: Optional[threading.Timer] = None
        self._usage_timer: Optional[threading.Timer] = None
        self._schedule_balance_poll()
        if self._usage_api is not None:
            self._schedule_usage_poll()

        # Run initial poll in background so the tray shows up immediately
        threading.Thread(target=self._do_poll, daemon=True).start()
        if self._usage_api is not None:
            threading.Thread(target=self._do_usage_poll, daemon=True).start()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _make_menu(self) -> pystray.Menu:
        items: list = []

        if self._last_balance is not None:
            b = self._last_balance
            sym = b.symbol
            items.append(pystray.MenuItem(
                f"Balance: {sym}{b.total_balance:.2f}", None, enabled=False,
            ))
            items.append(pystray.MenuItem(
                f"  Topped-up: {sym}{b.topped_up_balance:.2f}", None, enabled=False,
            ))
            items.append(pystray.MenuItem(
                f"  Granted: {sym}{b.granted_balance:.2f}", None, enabled=False,
            ))
            items.append(pystray.Menu.SEPARATOR)
            items.append(pystray.MenuItem(
                f"Today: {sym}{self._store.today_consumption():.2f}",
                None, enabled=False,
            ))
            ts = self._store.latest_update_time()
            if ts:
                items.append(pystray.MenuItem(
                    f"Updated: {ts}", None, enabled=False,
                ))
        else:
            items.append(pystray.MenuItem("Loading ...", None, enabled=False))

        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem(
            "Open Control Panel", self._on_open_panel, default=True,
        ))
        items.append(pystray.MenuItem("Refresh", self._on_refresh))
        items.append(pystray.MenuItem("Charge", self._on_charge))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Settings", self._on_settings))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quit", self._on_quit))

        return pystray.Menu(*items)

    def _refresh_display(self, balance: BalanceInfo) -> None:
        """Update icon, tooltip, and menu after a successful poll."""
        self._last_balance = balance
        sym = balance.symbol
        total = balance.total_balance

        if total <= self._config.alert_threshold_red:
            state = "danger"
        elif total <= self._config.alert_threshold_yellow:
            state = "warning"
        else:
            state = "normal"

        self._tray.icon = _make_icon(f"{sym}{total:.2f}", state)

        today = self._store.today_consumption()
        self._tray.title = (
            f"PanelWhale\n"
            f"Balance: {sym}{total:.2f}\n"
            f"Today: {sym}{today:.2f}"
        )

        self._tray.menu = self._make_menu()
        self._check_alert(total, sym)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _check_alert(self, total: float, sym: str) -> None:
        if total <= self._config.alert_threshold_red:
            new_state = "red"
            if self._alert_state != "red":
                self._tray.notify(
                    f"Only {sym}{total:.2f} remaining. Top up immediately.",
                    "Balance Critical",
                )
        elif total <= self._config.alert_threshold_yellow:
            new_state = "yellow"
            if self._alert_state not in ("yellow", "red"):
                self._tray.notify(
                    f"{sym}{total:.2f} remaining. Consider topping up.",
                    "Balance Low",
                )
        else:
            new_state = None
        self._alert_state = new_state

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _schedule_balance_poll(self) -> None:
        self._balance_timer = threading.Timer(
            self._config.poll_interval_seconds, self._on_balance_timer,
        )
        self._balance_timer.daemon = True
        self._balance_timer.start()

    def _schedule_usage_poll(self) -> None:
        self._usage_timer = threading.Timer(
            self._config.usage_poll_interval_seconds, self._on_usage_timer,
        )
        self._usage_timer.daemon = True
        self._usage_timer.start()

    def _on_balance_timer(self) -> None:
        if not self._shutting_down:
            self._do_poll()
            self._schedule_balance_poll()

    def _on_usage_timer(self) -> None:
        if not self._shutting_down and self._usage_api is not None:
            self._do_usage_poll()
            self._schedule_usage_poll()

    def _do_poll(self) -> None:
        try:
            balance = self._api.get_balance()
        except APIError as e:
            log.warning("API poll failed: %s", e)
            self._tray.icon = _make_icon("ERR", "loading")
            self._tray.title = "PanelWhale — Connection failed"
            return
        self._store.add(balance)
        self._refresh_display(balance)

    def _do_usage_poll(self) -> None:
        from datetime import datetime
        from monitor.usage_api import UsageAPIError
        from monitor.usage_cache import save_usage, load_usage

        try:
            now = datetime.now()
            usage = self._usage_api.get_monthly_usage(now.month, now.year)
            save_usage(usage)
        except UsageAPIError as e:
            log.warning("Usage poll failed: %s", e)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _on_open_panel(self, icon, item) -> None:
        threading.Thread(target=self._open_panel, daemon=True).start()

    def _open_panel(self) -> None:
        from monitor.panel import generate_control_panel
        try:
            path = generate_control_panel(
                self._config, self._api, self._usage_api, self._store,
            )
            os.startfile(path)
        except Exception:
            log.exception("Failed to generate control panel")
            try:
                self._tray.notify(
                    "Failed to generate control panel.", "PanelWhale Error",
                )
            except Exception:
                pass

    def _on_refresh(self, icon, item) -> None:
        now = time.time()
        if now - self._last_manual_refresh < 15:
            return
        self._last_manual_refresh = now
        threading.Thread(target=self._do_poll, daemon=True).start()
        if self._usage_api is not None:
            threading.Thread(target=self._do_usage_poll, daemon=True).start()

    def _on_charge(self, icon, item) -> None:
        webbrowser.open("https://platform.deepseek.com/top_up")

    def _on_settings(self, icon, item) -> None:
        config_dir = get_config_dir()
        config_path = os.path.join(config_dir, "config.yaml")
        if not os.path.isfile(config_path):
            os.makedirs(config_dir, exist_ok=True)
            save_config(self._config, config_path)
        os.startfile(config_path)

    def _on_quit(self, icon, item) -> None:
        self._shutting_down = True
        if self._balance_timer is not None:
            self._balance_timer.cancel()
        if self._usage_timer is not None:
            self._usage_timer.cancel()

        try:
            balance = self._api.get_balance()
            self._store.end_session(balance)
        except APIError as e:
            log.warning("Final poll failed during shutdown: %s", e)
            self._store.flush()

        icon.stop()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the pystray event loop (blocks until quit)."""
        self._tray.run()
