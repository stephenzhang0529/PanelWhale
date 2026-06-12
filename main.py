#!/usr/bin/env python3
"""DeepSeek API Usage Monitor — cross-platform system-tray indicator.

Linux : AppIndicator3 / AyatanaAppIndicator3  (GTK 3)
Windows : pystray + Pillow
"""

import os
import sys
import logging

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

from monitor.config import load_config
from monitor.api import DeepSeekAPI
from monitor.store import BalanceStore

log = logging.getLogger("deepseek-monitor")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = load_config()

    if not config.api_key:
        log.error(
            "No API key configured.  Set it in config.yaml or the "
            "DEEPSEEK_API_KEY environment variable."
        )
        sys.exit(1)

    api = DeepSeekAPI(config.api_key)
    store = BalanceStore()

    store.start_session()
    log.info("Session started — today_from_logs=¥%.2f", store.today_from_logs)

    if sys.platform == "win32":
        from monitor.indicator_win import WinBalanceIndicator
        indicator = WinBalanceIndicator(config, api, store)
        indicator.run()
    else:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from monitor.indicator import BalanceIndicator

        BalanceIndicator(config, api, store)
        Gtk.main()


if __name__ == "__main__":
    main()
