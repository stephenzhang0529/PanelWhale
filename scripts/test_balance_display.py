#!/usr/bin/env python3
"""Quick visual test for balance indicator colours.

Usage:
  python3 scripts/test_balance_display.py 0.50   # red
  python3 scripts/test_balance_display.py 3.00   # yellow
  python3 scripts/test_balance_display.py 108.00 # normal
  python3 scripts/test_balance_display.py        # cycle through all 3 states (10s each)

Stop the real monitor first:
  systemctl --user stop panelwhale
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, GLib

from monitor.config import Config
from monitor.store import BalanceStore
from monitor.indicator import BalanceIndicator


class MockAPI:
    """Returns a fixed balance instead of calling the real API."""

    def __init__(self, total: float, currency: str = "CNY"):
        from monitor.api import BalanceInfo
        self._balance = BalanceInfo(
            is_available=True,
            total_balance=total,
            granted_balance=0.0,
            topped_up_balance=total,
            currency=currency,
        )

    def get_balance(self):
        return self._balance


class MockStore(BalanceStore):
    """A store that never tries to write logs to disk."""

    def __init__(self):
        # Skip disk I/O – override parent init
        self._session_records = []
        self._session_consumption = 0.0
        self._last_balance = None
        self._last_ts = None
        self.today_from_logs = 0.0
        self._log_path = None
        self._log_entries = []

    def start_session(self) -> None:
        pass

    def end_session(self, balance) -> None:
        pass

    def add(self, balance) -> None:
        self._last_balance = balance.total_balance
        self._last_ts = time.time()
        from monitor.store import BalanceRecord
        self._session_records.append(
            BalanceRecord(
                timestamp=self._last_ts,
                total=balance.total_balance,
                granted=balance.granted_balance,
                topped_up=balance.topped_up_balance,
            )
        )


def run_single(total: float):
    """Display the indicator with a fixed balance until the user quits."""
    config = Config(
        api_key="test",
        poll_interval_seconds=300,
        alert_threshold_yellow=5.0,
        alert_threshold_red=1.0,
    )
    api = MockAPI(total)
    store = MockStore()
    store.start_session()

    print(f"Balance: ¥{total:.2f} — "
          + ("RED (danger)" if total <= 1.0
             else "YELLOW (warning)" if total <= 5.0
             else "NORMAL"))
    print("Right-click → Quit to exit, or Ctrl+C in terminal.")
    print()

    BalanceIndicator(config, api, store)
    Gtk.main()


def run_cycle():
    """Cycle through all three states: 10s normal, 10s yellow, 10s red."""
    config = Config(
        api_key="test",
        poll_interval_seconds=10,
        alert_threshold_yellow=5.0,
        alert_threshold_red=1.0,
    )
    store = MockStore()
    store.start_session()

    states = [
        (108.32, "NORMAL (> ¥5)"),
        (3.50, "YELLOW (¥1–5)"),
        (0.80, "RED (< ¥1)"),
    ]

    class CyclingAPI:
        def __init__(self):
            self._idx = 0
            self._api = None
            self._cycle()

        def _cycle(self):
            total, label = states[self._idx]
            print(f"[{self._idx+1}/{len(states)}] {label}: ¥{total:.2f}")
            self._api = MockAPI(total)

        def get_balance(self):
            balance = self._api.get_balance()
            self._idx = (self._idx + 1) % len(states)
            self._cycle()
            return balance

    api = CyclingAPI()
    indicator = BalanceIndicator(config, api, store)

    print("Cycling through all 3 states every 10 seconds…")
    print("Right-click → Quit to exit.")
    print()

    Gtk.main()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            total = float(sys.argv[1])
        except ValueError:
            print(f"Invalid balance: {sys.argv[1]}")
            sys.exit(1)
        run_single(total)
    else:
        run_cycle()
