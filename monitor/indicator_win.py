"""Windows system-tray indicator using pystray + Pillow.

Replaces AppIndicator3/GTK with a cross-platform tray icon.
The tray icon shows a coloured status dot overlaid on the DeepSeek logo;
balance details and consumption stats appear in the right-click menu.
"""

import os
import sys
import time
import logging
import threading
import signal
from typing import Optional

from PIL import Image, ImageDraw

from monitor.config import Config
from monitor.api import DeepSeekAPI, APIError, BalanceInfo
from monitor.store import BalanceStore

log = logging.getLogger(__name__)

# ---- Status colours ----
_COLOR_NORMAL = (52, 199, 89)      # green
_COLOR_WARNING = (255, 204, 0)     # yellow
_COLOR_DANGER = (255, 59, 48)      # red
_COLOR_ERROR = (142, 142, 147)     # grey

_ICON_SIZE = 64
_DOT_RADIUS = _ICON_SIZE // 5
_DOT_MARGIN = 3

# ---- Locate DeepSeek logo ----
_BASE_ICON = None
for _candidate in (
    os.path.join(os.path.dirname(__file__), "..", "deepseek-color.png"),
    os.path.join(os.path.dirname(sys.executable), "deepseek-color.png"),
):
    if os.path.isfile(_candidate):
        try:
            _BASE_ICON = Image.open(_candidate).convert("RGBA").resize((_ICON_SIZE, _ICON_SIZE))
            break
        except Exception:
            pass


def _make_icon(color: tuple) -> Image.Image:
    """Return a tray icon: DeepSeek logo + coloured status dot, or a plain dot."""
    if _BASE_ICON:
        img = _BASE_ICON.copy()
    else:
        img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        cx = _ICON_SIZE // 2
        cy = _ICON_SIZE // 2
        r = _ICON_SIZE // 3
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        return img

    # Overlay status dot on bottom-right corner
    draw = ImageDraw.Draw(img)
    x1 = _ICON_SIZE - 2 * _DOT_RADIUS - _DOT_MARGIN
    y1 = _ICON_SIZE - 2 * _DOT_RADIUS - _DOT_MARGIN
    x2 = _ICON_SIZE - _DOT_MARGIN
    y2 = _ICON_SIZE - _DOT_MARGIN
    draw.ellipse((x1, y1, x2, y2), fill=color, outline=(255, 255, 255, 200), width=1)
    return img


# ---- Desktop notification (best-effort) ----

def _desktop_notify(title: str, message: str) -> None:
    """Show a desktop notification, falling back to the log."""
    # plyer (cross-platform)
    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="DeepSeek Monitor", timeout=5)
        return
    except Exception:
        pass

    # winotify (Windows-only, lightweight)
    if sys.platform == "win32":
        try:
            from winotify import Notification  # type: ignore
            toast = Notification(app_id="DeepSeek Monitor",
                                 title=title, msg=message)
            toast.show()
            return
        except Exception:
            pass

    log.info("ALERT — %s: %s", title, message)


# ------------------------------------------------------------------
# Indicator
# ------------------------------------------------------------------

class WinBalanceIndicator:
    """System-tray indicator for Windows (also works on Linux with pystray)."""

    def __init__(self, config: Config, api: DeepSeekAPI, store: BalanceStore):
        self._config = config
        self._api = api
        self._store = store
        self._alert_state: Optional[str] = None          # None | "yellow" | "red"
        self._shutting_down = False
        self._last_manual_refresh: float = 0.0
        self._stop_event = threading.Event()

        import pystray

        self._tray_icon = pystray.Icon(
            "deepseek-monitor",
            _make_icon(_COLOR_ERROR),
            "DeepSeek Monitor — loading ...",
            self._build_initial_menu(),
        )
        self._setup_shutdown()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_initial_menu(self):
        import pystray
        return pystray.Menu(
            pystray.MenuItem("Loading ...", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _rebuild_menu(self, balance: BalanceInfo) -> None:
        import pystray
        sym = balance.symbol
        total = balance.total_balance

        c5 = self._store.consumption_since(5)
        c30 = self._store.consumption_since(30)
        c180 = self._store.consumption_since(180)
        today = self._store.today_consumption()
        updated = self._store.latest_update_time() or "---"

        def _c(v): return f"{sym}{v:.2f}" if v is not None else "---"

        self._tray_icon.menu = pystray.Menu(
            pystray.MenuItem(f"Total :   {sym}{total:.2f}", None, enabled=False),
            pystray.MenuItem(f"  Topped-up : {sym}{balance.topped_up_balance:.2f}", None, enabled=False),
            pystray.MenuItem(f"  Granted :   {sym}{balance.granted_balance:.2f}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Last 5 min :  {_c(c5)}", None, enabled=False),
            pystray.MenuItem(f"Last 30 min : {_c(c30)}", None, enabled=False),
            pystray.MenuItem(f"Last 3 hr :   {_c(c180)}", None, enabled=False),
            pystray.MenuItem(f"Today :       {sym}{today:.2f}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Updated : {updated}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh", self._on_manual_refresh, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _rebuild_error_menu(self) -> None:
        import pystray
        self._tray_icon.menu = pystray.Menu(
            pystray.MenuItem("API Error — will retry", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh", self._on_manual_refresh, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _setup_shutdown(self) -> None:
        import atexit
        atexit.register(self._shutdown_gracefully)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, AttributeError):
                pass  # SIGTERM doesn't exist on Windows

    def _on_signal(self, signum, _frame) -> None:
        log.info("Signal %d — shutting down", signum)
        self._shutdown_gracefully()
        self._tray_icon.stop()

    def _on_quit(self, icon, _item=None) -> None:
        log.info("Quit from menu")
        self._shutdown_gracefully()
        icon.stop()

    def _on_manual_refresh(self, _icon, _item=None) -> None:
        now = time.time()
        if now - self._last_manual_refresh < 15:
            return
        self._last_manual_refresh = now
        self._do_poll()

    def _shutdown_gracefully(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._stop_event.set()
        try:
            balance = self._api.get_balance()
            self._store.end_session(balance)
        except APIError as e:
            log.warning("Final poll failed during shutdown: %s", e)
            self._store.flush()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _do_poll(self) -> None:
        try:
            balance = self._api.get_balance()
        except APIError as e:
            log.warning("API poll failed: %s", e)
            self._tray_icon.icon = _make_icon(_COLOR_ERROR)
            self._tray_icon.title = "DeepSeek Monitor — API Error"
            self._rebuild_error_menu()
            return

        self._store.add(balance)
        total = balance.total_balance
        sym = balance.symbol

        # Status colour
        if total > self._config.alert_threshold_yellow:
            color = _COLOR_NORMAL
        elif total > self._config.alert_threshold_red:
            color = _COLOR_WARNING
        else:
            color = _COLOR_DANGER

        self._tray_icon.icon = _make_icon(color)
        self._tray_icon.title = f"DeepSeek  {sym}{total:.2f}"
        self._rebuild_menu(balance)
        self._check_alert(total, sym)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _check_alert(self, total: float, sym: str) -> None:
        if total <= self._config.alert_threshold_red:
            new_state = "red"
            if self._alert_state != "red":
                _desktop_notify(
                    "Balance Critical!",
                    f"DeepSeek balance is {sym}{total:.2f}. Top up immediately.",
                )
        elif total <= self._config.alert_threshold_yellow:
            new_state = "yellow"
            if self._alert_state not in ("yellow", "red"):
                _desktop_notify(
                    "Balance Low",
                    f"DeepSeek balance is {sym}{total:.2f}. Consider topping up.",
                )
        else:
            new_state = None
        self._alert_state = new_state

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking call — starts the polling thread and the tray-icon event loop."""

        def _poll_loop() -> None:
            self._do_poll()  # fire immediately
            while not self._stop_event.wait(timeout=self._config.poll_interval_seconds):
                if not self._shutting_down:
                    self._do_poll()

        threading.Thread(target=_poll_loop, daemon=True, name="poll-thread").start()
        self._tray_icon.run()
