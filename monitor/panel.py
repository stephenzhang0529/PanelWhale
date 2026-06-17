"""Interactive control panel generator for PanelWhale.

Renders a 3-column HTML dashboard with live data injected and opens it in
the default browser.  Called from the panel indicator's right-click menu.
"""

import os
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from monitor.config import Config
from monitor.api import DeepSeekAPI, APIError, BalanceInfo
from monitor.store import BalanceStore
from monitor.report import DailySummaryStore

log = logging.getLogger(__name__)

_DATA_ROOT = os.path.expanduser("~/.local/share/panelwhale")
_PANEL_DIR = os.path.join(_DATA_ROOT, "panel")
_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "panel_template.html")

# Currency mapping
_CURRENCY_MAP = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def generate_control_panel(
    config: Config,
    api: DeepSeekAPI,
    usage_api,
    store: BalanceStore,
) -> str:
    """Generate the control panel HTML and return its file path.

    Opens the file in the default browser.
    """
    # 1. Fetch balance -------------------------------------------------
    balance = _fetch_balance(api)

    # 2. Daily summaries (7 days) --------------------------------------
    today = date.today()
    week_ago = today - timedelta(days=6)
    summaries = DailySummaryStore.load_range(week_ago, today)

    # 3. Usage data ----------------------------------------------------
    usage = _fetch_usage(usage_api)
    has_usage = usage is not None

    # 4. Currency symbol -----------------------------------------------
    sym = _CURRENCY_MAP.get(
        balance.currency if balance else "CNY", "¥"
    )

    # 5. Compute chart data --------------------------------------------
    DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # -- Daily consumption: prefer usage API costs when available ------
    daily_dates: list[str] = []
    daily_values: list[float] = []

    # Build a date → total_cost lookup from usage API daily data
    _usage_cost_by_date: dict[str, float] = {}
    if has_usage:
        for day_entry in usage.daily:
            day_cost = sum(
                m.total_cost for m in day_entry.get("models", {}).values()
            )
            _usage_cost_by_date[day_entry["date"]] = round(day_cost, 4)

    for s in summaries:
        dt = datetime.strptime(s.date, "%Y-%m-%d")
        daily_dates.append(f"{DAY_LABELS[dt.weekday()]} {dt.month}/{dt.day}")
        if s.date in _usage_cost_by_date:
            # Use usage API cost data (more accurate)
            daily_values.append(_usage_cost_by_date[s.date])
        elif has_usage and _usage_cost_by_date:
            # Usage token is configured but this day has no data yet → 0
            daily_values.append(0.0)
        else:
            # Fall back to local balance-polling summary
            daily_values.append(round(s.total_consumption, 4))

    # -- Hourly: still from local summaries (usage API has no hourly) ---
    hourly_avg = [0.0] * 24
    for s in summaries:
        for h in range(24):
            hourly_avg[h] += s.hourly[h]
    hourly_avg = [round(v / 7, 6) for v in hourly_avg]
    hourly_labels = [f"{h:02d}:00" for h in range(24)]

    # 6. Usage-dependent data ------------------------------------------
    # (has_usage already computed above)
    cache_hit_chart = "{}"
    flash_daily_chart = "{}"
    pro_daily_chart = "{}"
    flash_tokens = "—"
    flash_cache_hit_rate = "0"
    flash_cost = "0.00"
    flash_efficiency = "—"
    flash_requests = "—"
    flash_tokens_short = "—"
    pro_tokens = "—"
    pro_cache_hit_rate = "0"
    pro_cost = "0.00"
    pro_efficiency = "—"
    pro_requests = "—"
    pro_tokens_short = "—"
    overall_cache_hit = "0"
    overall_cache_total = "0"
    mtd_cost = "--"

    if has_usage:
        mtd_cost = f"{sym}{usage.total_cost:.2f}"
        # Build daily chart data per model
        ch_dates: list[str] = []
        ch_hit: list[int] = []
        ch_miss: list[int] = []
        ch_output: list[int] = []
        f_hit: list[int] = []
        f_miss: list[int] = []
        f_output: list[int] = []
        p_hit: list[int] = []
        p_miss: list[int] = []
        p_output: list[int] = []

        daily_by_date = {e["date"]: e for e in usage.daily}
        for s in summaries:
            dt = datetime.strptime(s.date, "%Y-%m-%d")
            label = f"{DAY_LABELS[dt.weekday()]} {dt.month}/{dt.day}"
            ch_dates.append(label)
            day = daily_by_date.get(s.date, {})
            f = (day.get("models") or {}).get("flash")
            p = (day.get("models") or {}).get("pro")
            fh = int(f.cache_hit_tokens) if f else 0
            fm = int(f.cache_miss_tokens) if f else 0
            fo = int(f.response_tokens) if f else 0
            ph = int(p.cache_hit_tokens) if p else 0
            pm = int(p.cache_miss_tokens) if p else 0
            po = int(p.response_tokens) if p else 0
            ch_hit.append(fh + ph)
            ch_miss.append(fm + pm)
            ch_output.append(fo + po)
            f_hit.append(fh)
            f_miss.append(fm)
            f_output.append(fo)
            p_hit.append(ph)
            p_miss.append(pm)
            p_output.append(po)

        cache_hit_chart = json.dumps({
            "dates": ch_dates,
            "hit": ch_hit, "miss": ch_miss, "output": ch_output,
        }, ensure_ascii=False)
        flash_daily_chart = json.dumps({
            "dates": ch_dates,
            "hit": f_hit, "miss": f_miss, "output": f_output,
        }, ensure_ascii=False)
        pro_daily_chart = json.dumps({
            "dates": ch_dates,
            "hit": p_hit, "miss": p_miss, "output": p_output,
        }, ensure_ascii=False)

        # Model summaries
        fm = usage.models.get("flash")
        pm = usage.models.get("pro")
        if fm:
            flash_tokens = f"{fm.total_tokens:,}"
            flash_tokens_short = _short_num(fm.total_tokens)
            flash_cache_hit_rate = f"{fm.cache_hit_rate * 100:.0f}"
            flash_cost = f"{fm.total_cost:.2f}"
            flash_efficiency = (
                _short_num(int(fm.total_tokens / fm.total_cost))
                if fm.total_cost > 0 else "—"
            )
            flash_requests = f"{fm.request_count:,}"
        if pm:
            pro_tokens = f"{pm.total_tokens:,}"
            pro_tokens_short = _short_num(pm.total_tokens)
            pro_cache_hit_rate = f"{pm.cache_hit_rate * 100:.0f}"
            pro_cost = f"{pm.total_cost:.2f}"
            pro_efficiency = (
                _short_num(int(pm.total_tokens / pm.total_cost))
                if pm.total_cost > 0 else "—"
            )
            pro_requests = f"{pm.request_count:,}"

        # Overall cache stats
        total_hit = sum(m.cache_hit_tokens for m in usage.models.values())
        total_miss = sum(m.cache_miss_tokens for m in usage.models.values())
        denom = total_hit + total_miss
        overall_cache_hit = f"{(total_hit / denom * 100):.0f}" if denom > 0 else "0"
        overall_cache_total = _short_num(total_hit + total_miss)

    # 7. Render template -----------------------------------------------
    generated_at = datetime.now(_LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

    # Read template
    for candidate in (_TEMPLATE_PATH, "/opt/panelwhale/monitor/panel_template.html"):
        if os.path.isfile(candidate):
            template_path = candidate
            break
    else:
        raise FileNotFoundError("panel_template.html not found")

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Apply conditional blocks first
    html = _apply_conditionals(html, has_usage)

    # Simple replacements
    replacements = {
        "CURRENCY": sym,
        "BALANCE_TOTAL": f"{balance.total_balance:.2f}" if balance else "--",
        "BALANCE_TOPPED_UP": f"{balance.topped_up_balance:.2f}" if balance else "--",
        "BALANCE_GRANTED": f"{balance.granted_balance:.2f}" if balance else "--",
        "AVAILABLE": "true" if (balance and balance.is_available) else "false",
        "AVAILABLE_COLOR": "#4caf50" if (balance and balance.is_available) else "#e53935",
        "AVAILABLE_TEXT": "Available" if (balance and balance.is_available) else "Unavailable",
        "TODAY_CONSUMPTION": f"{store.today_consumption():.2f}",
        "MTD_COST": mtd_cost,
        "HAS_USAGE": "true" if has_usage else "false",
        "FLASH_TOKENS": flash_tokens,
        "FLASH_CACHE_HIT_RATE": flash_cache_hit_rate,
        "FLASH_COST": flash_cost,
        "FLASH_EFFICIENCY": flash_efficiency,
        "FLASH_REQUESTS": flash_requests,
        "FLASH_TOKENS_SHORT": flash_tokens_short,
        "PRO_TOKENS": pro_tokens,
        "PRO_CACHE_HIT_RATE": pro_cache_hit_rate,
        "PRO_COST": pro_cost,
        "PRO_EFFICIENCY": pro_efficiency,
        "PRO_REQUESTS": pro_requests,
        "PRO_TOKENS_SHORT": pro_tokens_short,
        "OVERALL_CACHE_HIT": overall_cache_hit,
        "OVERALL_CACHE_TOTAL": overall_cache_total,
        "CACHE_HIT_CHART": cache_hit_chart,
        "DAILY_CHART_DATA": json.dumps(
            {"dates": daily_dates, "values": daily_values}, ensure_ascii=False
        ),
        "HOURLY_CHART_DATA": json.dumps(
            {"hours": hourly_labels, "values": hourly_avg}, ensure_ascii=False
        ),
        "FLASH_DAILY_CHART": flash_daily_chart,
        "PRO_DAILY_CHART": pro_daily_chart,
        "GENERATED_AT": generated_at,
    }

    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", str(value))

    # 8. Write to disk -------------------------------------------------
    os.makedirs(_PANEL_DIR, exist_ok=True)
    panel_path = os.path.join(_PANEL_DIR, "panel.html")
    with open(panel_path, "w", encoding="utf-8") as f:
        f.write(html)

    log.info("Control panel generated: %s", panel_path)
    return panel_path


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _fetch_balance(api: DeepSeekAPI) -> Optional[BalanceInfo]:
    """Fetch balance, returning None on failure."""
    try:
        return api.get_balance()
    except APIError as e:
        log.warning("Panel: balance fetch failed: %s", e)
        return None


def _fetch_usage(usage_api) -> Optional[object]:
    """Fetch or load cached usage data.  Returns None if unavailable."""
    if usage_api is None:
        return None

    from monitor.usage_api import UsageAPIError
    from monitor.usage_cache import load_usage, save_usage as cache_save

    today = datetime.now()
    try:
        cached = load_usage()
        if cached and cached.month == today.month and cached.year == today.year:
            log.debug("Panel: using cached usage data")
            return cached
        log.debug("Panel: fetching fresh usage data")
        monthly = usage_api.get_monthly_usage(today.month, today.year)
        cache_save(monthly)
        return monthly
    except UsageAPIError as e:
        log.warning("Panel: usage fetch failed: %s", e)
        # Try stale cache as fallback
        return load_usage()
    except Exception as e:
        log.warning("Panel: unexpected usage error: %s", e)
        return load_usage()


def _short_num(n: int) -> str:
    """Format a number with K/M/B suffix."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _apply_conditionals(html: str, has_usage: bool) -> str:
    """Strip or keep ``{{#HAS_USAGE}}`` / ``{{^HAS_USAGE}}`` blocks.

    When *has_usage* is True, ``{{^HAS_USAGE}}...{{/HAS_USAGE}}`` blocks
    are removed (keeping ``{{#HAS_USAGE}}...{{/HAS_USAGE}}`` content).
    When False, the inverse.
    """
    import re

    if has_usage:
        # Remove {{^HAS_USAGE}}...{{/HAS_USAGE}} blocks
        html = re.sub(
            r'\{\{\^HAS_USAGE\}\}.*?\{\{/HAS_USAGE\}\}',
            '', html, flags=re.DOTALL
        )
        # Remove the tags themselves
        html = html.replace("{{#HAS_USAGE}}", "").replace("{{/HAS_USAGE}}", "")
    else:
        # Remove {{#HAS_USAGE}}...{{/HAS_USAGE}} blocks
        html = re.sub(
            r'\{\{#HAS_USAGE\}\}.*?\{\{/HAS_USAGE\}\}',
            '', html, flags=re.DOTALL
        )
        # Keep {{^HAS_USAGE}} content, just remove the tags
        html = html.replace("{{^HAS_USAGE}}", "").replace("{{/HAS_USAGE}}", "")

    return html
