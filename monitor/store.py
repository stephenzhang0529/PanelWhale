import os
import sys
import json
import time
import bisect
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional

from monitor.api import BalanceInfo


LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

if sys.platform == "win32":
    _DATA_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "deepseek-monitor")
else:
    _DATA_ROOT = os.path.expanduser("~/.local/share/deepseek-monitor")
_LOGS_DIR = os.path.join(_DATA_ROOT, "logs")

# Retention: keep log files for this many days
_LOG_RETENTION_DAYS = 7


# ------------------------------------------------------------------
# Log-file helpers
# ------------------------------------------------------------------

def _ensure_dirs() -> None:
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _today_str() -> str:
    """Return today's date string, e.g. '2026-06-11'."""
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def _log_filename(start_iso: str) -> str:
    """Sanitised filename from a session-start ISO timestamp."""
    safe = start_iso.replace(":", "-")
    return f"{safe}.json"


def _parse_today_sum(log_path: str) -> float:
    """Extract `sum_consumption` from a single log file. Returns 0 on any failure."""
    try:
        with open(log_path, "r") as f:
            data = json.load(f)
        return float(data.get("sum_consumption", 0))
    except Exception:
        return 0


# ------------------------------------------------------------------
# BalanceRecord (session-only)
# ------------------------------------------------------------------

class BalanceRecord:
    __slots__ = ("timestamp", "total", "granted", "topped_up")

    def __init__(self, timestamp: float, total: float, granted: float, topped_up: float):
        self.timestamp = timestamp
        self.total = total
        self.granted = granted
        self.topped_up = topped_up


# ------------------------------------------------------------------
# BalanceStore
# ------------------------------------------------------------------

class BalanceStore:
    """Session-log-based balance store.

    * On startup: scan today's log files, accumulate sum_consumption →
      `today_from_logs`.  Create a new session log.
    * Every 5 min: `add(balance)` appends an in-memory record and writes
      a consumption entry to the session log.
    * On shutdown: `end_session(balance)` polls one last time, writes the
      final consumption, and flushes `sum_consumption` to the log.
    * Short-window queries (5m / 30m / 3h) use *current-session*
      in-memory records with best-effort fallback to the oldest available
      record.
    """

    def __init__(self):
        _ensure_dirs()
        self._session_records: list[BalanceRecord] = []
        self._session_consumption: float = 0.0
        self._last_balance: Optional[float] = None
        self._last_ts: Optional[float] = None

        # Accumulated sum_consumption from today's previous sessions
        self.today_from_logs: float = 0.0

        # Current log file path
        self._log_path: Optional[str] = None

        # In-memory entries (for writing to log at end)
        self._log_entries: list[dict] = []

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """Call once on startup.  Scan today's logs, create a new log file."""
        self._scan_today_logs()
        self._cleanup_old_logs()
        self._create_log()

    def end_session(self, balance: BalanceInfo) -> None:
        """Call on shutdown.  Record final consumption and write SUM."""
        if self._last_balance is None:
            # No records at all this session — nothing to write
            return

        now = time.time()
        consumption = max(0.0, self._last_balance - balance.total_balance)
        self._session_consumption += consumption
        self._last_balance = balance.total_balance
        self._last_ts = now

        # Append final entry
        self._log_entries.append({
            "ts": datetime.fromtimestamp(now, tz=LOCAL_TZ).isoformat(timespec="seconds"),
            "consumption": round(consumption, 6),
            "balance": balance.total_balance,
        })

        # Also add to in-memory records for UI consistency
        self._session_records.append(
            BalanceRecord(
                timestamp=now,
                total=balance.total_balance,
                granted=balance.granted_balance,
                topped_up=balance.topped_up_balance,
            )
        )

        self._write_log(final=True)

    def flush(self) -> None:
        """Force-write accumulated session data to the log with sum_consumption.

        Use this when the final API poll is impossible (e.g. network already
        down during shutdown) but we still need to preserve what we've
        recorded so far.
        """
        if self._log_path is None or not self._log_entries:
            return
        self._write_log(final=True)

    # ------------------------------------------------------------------
    # Periodic update
    # ------------------------------------------------------------------

    def add(self, balance: BalanceInfo) -> None:
        """Record a new balance snapshot (called every poll interval)."""
        now = time.time()
        total = balance.total_balance

        # Calculate consumption since last record
        if self._last_balance is not None:
            consumption = max(0.0, self._last_balance - total)
        else:
            consumption = 0.0

        self._session_consumption += consumption
        self._last_balance = total
        self._last_ts = now

        # In-memory
        self._session_records.append(
            BalanceRecord(
                timestamp=now,
                total=total,
                granted=balance.granted_balance,
                topped_up=balance.topped_up_balance,
            )
        )

        # Log entry
        self._log_entries.append({
            "ts": datetime.fromtimestamp(now, tz=LOCAL_TZ).isoformat(timespec="seconds"),
            "consumption": round(consumption, 6),
            "balance": total,
        })

        # Write incrementally (overwrite file each time — small enough)
        self._write_log(final=False)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current(self) -> Optional[BalanceRecord]:
        return self._session_records[-1] if self._session_records else None

    def consumption_since(self, minutes: int) -> Optional[float]:
        """Consumption in last N minutes from current-session data.

        Best-effort: if the oldest session record is newer than N minutes
        ago, use that oldest record as the baseline anyway.
        """
        if not self._session_records:
            return None

        target = time.time() - minutes * 60
        old = self._find_nearest(target)
        if old is None:
            return None

        latest = self._session_records[-1]
        delta = old.total - latest.total
        return max(0.0, delta)

    def today_consumption(self) -> float:
        """Total consumption today = sum from previous sessions (logs)
        plus consumption accumulated in the current session so far."""
        return round(self.today_from_logs + self._session_consumption, 6)

    def latest_update_time(self) -> Optional[str]:
        rec = self.current()
        if rec is None:
            return None
        dt = datetime.fromtimestamp(rec.timestamp, tz=LOCAL_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Internal: log scanning
    # ------------------------------------------------------------------

    def _scan_today_logs(self) -> None:
        """Sum up sum_consumption from all log files matching today's date."""
        today = _today_str()
        total = 0.0
        try:
            for fname in os.listdir(_LOGS_DIR):
                if not fname.startswith(today) or not fname.endswith(".json"):
                    continue
                path = os.path.join(_LOGS_DIR, fname)
                total += _parse_today_sum(path)
        except FileNotFoundError:
            pass
        self.today_from_logs = round(total, 6)

    def _cleanup_old_logs(self) -> None:
        """Remove log files older than _LOG_RETENTION_DAYS."""
        cutoff = datetime.now(LOCAL_TZ) - timedelta(days=_LOG_RETENTION_DAYS)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        try:
            for fname in os.listdir(_LOGS_DIR):
                path = os.path.join(_LOGS_DIR, fname)
                if not os.path.isfile(path):
                    continue
                # Extract date prefix from filename (YYYY-MM-DD)
                date_part = fname[:10]
                if date_part < cutoff_str:
                    os.remove(path)
        except FileNotFoundError:
            pass

    def _create_log(self) -> None:
        """Create a new session log file."""
        start_iso = _now_iso()
        fname = _log_filename(start_iso)
        self._log_path = os.path.join(_LOGS_DIR, fname)
        self._log_entries = []
        self._session_start = start_iso

    def _write_log(self, final: bool) -> None:
        """Write the log file. If final=True, include sum_consumption."""
        if not self._log_path:
            return
        data = {
            "session_start": self._session_start,
            "entries": self._log_entries,
        }
        if final:
            data["session_end"] = _now_iso()
            data["sum_consumption"] = round(self._session_consumption, 6)

        tmp = self._log_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._log_path)

    # ------------------------------------------------------------------
    # Internal: nearest-record search
    # ------------------------------------------------------------------

    def _find_nearest(self, target_ts: float) -> Optional[BalanceRecord]:
        if not self._session_records:
            return None
        timestamps = [r.timestamp for r in self._session_records]
        idx = bisect.bisect_left(timestamps, target_ts)
        if idx == 0:
            return self._session_records[0]
        if idx == len(self._session_records):
            return self._session_records[-1]
        before = self._session_records[idx - 1]
        after = self._session_records[idx]
        if abs(before.timestamp - target_ts) <= abs(after.timestamp - target_ts):
            return before
        return after
