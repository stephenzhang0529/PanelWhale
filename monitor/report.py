"""Daily summary storage for PanelWhale.

Provides:
- DailySummaryStore: tiered daily-summary storage (365-day retention)
- Used by the balance store (aggregate_today_from_logs) and the control
  panel generator (load_range for consumption charts).
"""

import os
import json
import logging
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional

from monitor.config import get_data_root

log = logging.getLogger(__name__)

_DATA_ROOT = get_data_root()
_LOGS_DIR = os.path.join(_DATA_ROOT, "logs")
_SUMMARIES_DIR = os.path.join(_DATA_ROOT, "daily_summaries")
_REPORTS_DIR = os.path.join(_DATA_ROOT, "reports")

_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo
_SUMMARY_RETENTION_DAYS = 365


# ------------------------------------------------------------------
# DailySummary
# ------------------------------------------------------------------


@dataclass
class DailySummary:
    date: str  # YYYY-MM-DD
    total_consumption: float = 0.0
    hourly: list = field(default_factory=lambda: [0.0] * 24)


# ------------------------------------------------------------------
# DailySummaryStore
# ------------------------------------------------------------------


class DailySummaryStore:
    """CRUD for daily-summary JSON files.

    Each file lives at ``daily_summaries/YYYY-MM-DD.json`` and stores
    total consumption + per-hour breakdown for a single calendar day.
    """

    # -- paths --------------------------------------------------------

    @staticmethod
    def _path_for(date_str: str) -> str:
        os.makedirs(_SUMMARIES_DIR, exist_ok=True)
        return os.path.join(_SUMMARIES_DIR, f"{date_str}.json")

    # -- load / save --------------------------------------------------

    @classmethod
    def _load(cls, path: str) -> Optional[DailySummary]:
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return DailySummary(
                date=data["date"],
                total_consumption=float(data.get("total_consumption", 0)),
                hourly=[float(h) for h in data.get("hourly", [0.0] * 24)],
            )
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return None

    @classmethod
    def _save(cls, path: str, summary: DailySummary) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(
                {
                    "date": summary.date,
                    "total_consumption": summary.total_consumption,
                    "hourly": summary.hourly,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        os.replace(tmp, path)

    @classmethod
    def load_range(cls, start_date: date, end_date: date) -> list[DailySummary]:
        """Return daily summaries for *start_date* through *end_date* (inclusive).

        Days without a summary file are returned as empty ``DailySummary`` objects.
        """
        results = []
        d = start_date
        while d <= end_date:
            date_str = d.strftime("%Y-%m-%d")
            s = cls._load(cls._path_for(date_str))
            results.append(s if s else DailySummary(date=date_str))
            d += timedelta(days=1)
        return results

    @classmethod
    def load_day(cls, day: date) -> DailySummary:
        """Return the summary for a single day (empty if missing)."""
        date_str = day.strftime("%Y-%m-%d")
        s = cls._load(cls._path_for(date_str))
        return s if s else DailySummary(date=date_str)

    # -- upsert -------------------------------------------------------

    @classmethod
    def upsert(cls, date_str: str, consumption: float, hour: int) -> None:
        """Add *consumption* to the hourly bucket *hour* (0–23) for *date_str*."""
        if consumption <= 0:
            return
        if not (0 <= hour < 24):
            return
        path = cls._path_for(date_str)
        summary = cls._load(path) or DailySummary(date=date_str)
        summary.total_consumption = round(summary.total_consumption + consumption, 6)
        summary.hourly[hour] = round(summary.hourly[hour] + consumption, 6)
        cls._save(path, summary)

    # -- aggregation --------------------------------------------------

    @classmethod
    def aggregate_today_from_logs(cls) -> None:
        """Re-build today's daily summary from raw session logs.

        Idempotent — deletes today's summary first, then re-aggregates
        all of today's session logs from scratch.  Safe to call on every
        startup and shutdown.
        """
        today_str = datetime.now(_LOCAL_TZ).strftime("%Y-%m-%d")
        today_path = cls._path_for(today_str)
        if os.path.isfile(today_path):
            os.remove(today_path)

        if not os.path.isdir(_LOGS_DIR):
            return

        for fname in sorted(os.listdir(_LOGS_DIR)):
            if not fname.startswith(today_str) or not fname.endswith(".json"):
                continue
            cls._process_log(os.path.join(_LOGS_DIR, fname))

    @classmethod
    def aggregate_all_raw_logs(cls) -> None:
        """Rebuild daily summaries for **all** dates covered by raw session logs.

        Fully idempotent: collects all entries first, deletes affected
        daily summaries, then re-aggregates.  Safe to call from the
        weekly timer script to catch any unprocessed data.
        """
        if not os.path.isdir(_LOGS_DIR):
            return

        # 1. Collect every entry from every raw log
        all_entries: list[tuple[str, int, float]] = []  # (date_str, hour, consumption)
        for fname in sorted(os.listdir(_LOGS_DIR)):
            if not fname.endswith(".json"):
                continue
            log_path = os.path.join(_LOGS_DIR, fname)
            if not os.path.isfile(log_path):
                continue
            all_entries.extend(cls._extract_entries(log_path))

        if not all_entries:
            return

        # 2. Delete summaries for every date that appears in the raw logs
        #    (this is what makes the operation idempotent)
        affected_dates: set[str] = {e[0] for e in all_entries}
        for date_str in affected_dates:
            path = cls._path_for(date_str)
            if os.path.isfile(path):
                os.remove(path)

        # 3. Re-aggregate
        for date_str, hour, consumption in all_entries:
            cls.upsert(date_str, consumption, hour)

        log.info(
            "Aggregated %d entries across %d date(s) from raw logs.",
            len(all_entries),
            len(affected_dates),
        )

    # -- internal helpers ---------------------------------------------

    @classmethod
    def _process_log(cls, log_path: str) -> None:
        """Aggregate a single session log into daily summaries (no cleanup)."""
        for date_str, hour, consumption in cls._extract_entries(log_path):
            cls.upsert(date_str, consumption, hour)

    @staticmethod
    def _extract_entries(log_path: str) -> list[tuple[str, int, float]]:
        """Parse a session log and return (date_str, hour, consumption) tuples."""
        try:
            with open(log_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        entries: list[tuple[str, int, float]] = []
        for entry in data.get("entries", []):
            consumption = float(entry.get("consumption", 0))
            if consumption <= 0:
                continue
            ts = entry.get("ts", "")
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_LOCAL_TZ)
            except (ValueError, TypeError):
                continue
            date_str = dt.strftime("%Y-%m-%d")
            entries.append((date_str, dt.hour, consumption))
        return entries

    # -- cleanup ------------------------------------------------------

    @classmethod
    def cleanup_old(cls) -> None:
        """Remove daily-summary files older than ``_SUMMARY_RETENTION_DAYS``."""
        cutoff = datetime.now(_LOCAL_TZ) - timedelta(days=_SUMMARY_RETENTION_DAYS)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        try:
            for fname in os.listdir(_SUMMARIES_DIR):
                path = os.path.join(_SUMMARIES_DIR, fname)
                if not os.path.isfile(path) or not fname.endswith(".json"):
                    continue
                if fname[:10] < cutoff_str:
                    os.remove(path)
                    log.debug("Cleaned up daily summary: %s", fname)
        except FileNotFoundError:
            pass

# End of report.py — DailySummaryStore is the public API.
