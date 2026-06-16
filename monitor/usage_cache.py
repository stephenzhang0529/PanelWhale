"""Persistent cache for DeepSeek platform usage data.

The usage APIs require a web-login Bearer token (not the API key) and data
changes slowly (monthly accumulation).  Caching lets the weekly report
script access usage data even when the panel monitor is not running.

Cache file: ``~/.local/share/panelwhale/usage_cache.json``
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from monitor.usage_api import MonthlyUsage, ModelUsage

log = logging.getLogger(__name__)

_DATA_ROOT = os.path.expanduser("~/.local/share/panelwhale")
_CACHE_FILE = os.path.join(_DATA_ROOT, "usage_cache.json")
_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


def save_usage(usage: MonthlyUsage) -> None:
    """Persist a ``MonthlyUsage`` snapshot to the cache file (atomic write)."""
    os.makedirs(_DATA_ROOT, exist_ok=True)

    data: dict = {
        "fetched_at": datetime.now(_LOCAL_TZ).isoformat(timespec="seconds"),
        "month": usage.month,
        "year": usage.year,
        "total_cost": usage.total_cost,
        "models": {
            key: {
                "model": m.model,
                "display_name": m.display_name,
                "request_count": m.request_count,
                "total_tokens": m.total_tokens,
                "cache_hit_tokens": m.cache_hit_tokens,
                "cache_miss_tokens": m.cache_miss_tokens,
                "response_tokens": m.response_tokens,
                "total_cost": m.total_cost,
            }
            for key, m in usage.models.items()
        },
        "daily": _serialise_daily(usage.daily),
    }

    tmp = _CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _CACHE_FILE)
        log.debug("Usage cache saved (%d/%d, ¥%.2f)",
                    usage.month, usage.year, usage.total_cost)
    except OSError as e:
        log.warning("Failed to write usage cache: %s", e)


def load_usage() -> Optional[MonthlyUsage]:
    """Load the cached usage snapshot, or ``None`` on any failure."""
    try:
        with open(_CACHE_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    try:
        models: dict = {}
        for key, mdata in data.get("models", {}).items():
            models[key] = ModelUsage(
                model=mdata["model"],
                display_name=mdata["display_name"],
                request_count=int(mdata.get("request_count", 0)),
                total_tokens=int(mdata.get("total_tokens", 0)),
                cache_hit_tokens=int(mdata.get("cache_hit_tokens", 0)),
                cache_miss_tokens=int(mdata.get("cache_miss_tokens", 0)),
                response_tokens=int(mdata.get("response_tokens", 0)),
                total_cost=float(mdata.get("total_cost", 0)),
            )

        daily = _deserialise_daily(data.get("daily", []))

        return MonthlyUsage(
            month=int(data["month"]),
            year=int(data["year"]),
            total_cost=float(data.get("total_cost", 0)),
            models=models,
            daily=daily,
        )
    except (KeyError, ValueError, TypeError) as e:
        log.warning("Usage cache corrupted: %s", e)
        return None


def get_cache_age_hours() -> Optional[float]:
    """Return hours since the cache was written, or ``None`` if no cache."""
    try:
        with open(_CACHE_FILE, "r") as f:
            data = json.load(f)
        fetched = datetime.fromisoformat(data["fetched_at"])
        now = datetime.now(_LOCAL_TZ)
        return (now - fetched).total_seconds() / 3600
    except Exception:
        return None


# ------------------------------------------------------------------
# Internal: serialise / deserialise daily list
# ------------------------------------------------------------------

def _serialise_daily(daily: list) -> list:
    """Convert ``ModelUsage`` objects inside daily entries to plain dicts."""
    out = []
    for entry in daily:
        day_out: dict = {"date": entry["date"], "models": {}}
        for key, mu in entry["models"].items():
            day_out["models"][key] = {
                "model": mu.model,
                "display_name": mu.display_name,
                "request_count": mu.request_count,
                "total_tokens": mu.total_tokens,
                "cache_hit_tokens": mu.cache_hit_tokens,
                "cache_miss_tokens": mu.cache_miss_tokens,
                "response_tokens": mu.response_tokens,
                "total_cost": mu.total_cost,
            }
        out.append(day_out)
    return out


def _deserialise_daily(raw: list) -> list:
    """Convert plain dicts back to ``ModelUsage`` objects inside daily entries."""
    out = []
    for entry in raw:
        day_out: dict = {"date": entry.get("date", ""), "models": {}}
        for key, mdata in entry.get("models", {}).items():
            day_out["models"][key] = ModelUsage(
                model=mdata.get("model", ""),
                display_name=mdata.get("display_name", ""),
                request_count=int(mdata.get("request_count", 0)),
                total_tokens=int(mdata.get("total_tokens", 0)),
                cache_hit_tokens=int(mdata.get("cache_hit_tokens", 0)),
                cache_miss_tokens=int(mdata.get("cache_miss_tokens", 0)),
                response_tokens=int(mdata.get("response_tokens", 0)),
                total_cost=float(mdata.get("total_cost", 0)),
            )
        out.append(day_out)
    return out
