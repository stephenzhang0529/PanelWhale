#!/usr/bin/env python3
"""DeepSeek API Usage Monitor — Ubuntu panel indicator.

Displays DeepSeek API balance in the top-panel status bar and refreshes
periodically.  See config.yaml for details.
"""

import os
import sys
import logging

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# Ensure the package is importable when run directly
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

from monitor.config import load_config
from monitor.api import DeepSeekAPI
from monitor.store import BalanceStore
from monitor.indicator import BalanceIndicator

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

    # Scan today's logs, create new session log
    store.start_session()
    log.info(
        "Session started — today_from_logs=¥%.2f", store.today_from_logs
    )

    # Create the indicator — this starts polling + shutdown hooks
    BalanceIndicator(config, api, store)

    # Let GTK own the process (signal handling via GLib.unix_signal_add)
    Gtk.main()


if __name__ == "__main__":
    main()
