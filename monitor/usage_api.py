"""DeepSeek platform usage API client.

Calls the internal platform.deepseek.com usage endpoints which require a
web-login Bearer token (NOT the API key used for /user/balance).

Usage::

    api = UsageAPI(usage_token)
    monthly = api.get_monthly_usage(6, 2026)
    print(f"MTD cost: ¥{monthly.total_cost:.2f}")
    for key, m in monthly.models.items():
        print(f"  {m.display_name}: {m.total_tokens:,} tokens, "
              f"{m.cache_hit_rate:.0%} cache hit")

Data model hierarchy (bottom-up)::

    ModelAmount  ─┐
    DailyAmount   ├── from /usage/amount
                   │
    ModelCost    ─┐
    DailyCost     ├── from /usage/cost
                   │
    ModelUsage   ─── merged token + cost for UI / reports
    MonthlyUsage ─── month-to-date snapshot (models dict + daily list)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests


# ------------------------------------------------------------------
# Endpoint URLs
# ------------------------------------------------------------------

PLATFORM_AMOUNT_URL = (
    "https://platform.deepseek.com/api/v0/usage/amount"
    "?month={month}&year={year}"
)
PLATFORM_COST_URL = (
    "https://platform.deepseek.com/api/v0/usage/cost"
    "?month={month}&year={year}"
)

# Map raw model ids to short display names (mirrors _CURRENCY_MAP in api.py)
_MODEL_DISPLAY = {
    "deepseek-v4-flash": "Flash",
    "deepseek-v4-pro": "Pro",
    "deepseek-reasoner": "Reasoner",
    "deepseek-chat": "Chat",
}


def _display_name(model: str) -> str:
    """Return a short display name for a model id, falling back to the raw id."""
    return _MODEL_DISPLAY.get(model, model)


def _model_key(model: str) -> str:
    """Normalise a model id to a short key: 'flash', 'pro', or the raw id."""
    for candidate in ("flash", "pro", "reasoner", "chat"):
        if candidate in model.lower():
            return candidate
    return model


# ------------------------------------------------------------------
# Data models — raw API responses
# ------------------------------------------------------------------


@dataclass
class ModelAmount:
    """Per-model token amounts returned by the /amount endpoint."""

    model: str  # e.g. "deepseek-v4-flash"
    request_count: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    prompt_tokens: int = 0  # prompt tokens NOT served from cache
    response_tokens: int = 0


@dataclass
class ModelCost:
    """Per-model cost returned by the /cost endpoint."""

    model: str
    cache_hit_cost: float = 0.0
    cache_miss_cost: float = 0.0
    response_cost: float = 0.0


@dataclass
class DailyAmount:
    """Single day's token data across models."""

    date: str  # "YYYY-MM-DD"
    models: list[ModelAmount] = field(default_factory=list)


@dataclass
class DailyCost:
    """Single day's cost data across models."""

    date: str
    models: list[ModelCost] = field(default_factory=list)


@dataclass
class UsageAmountResponse:
    """Top-level parse result from the /amount endpoint."""

    models: list[ModelAmount] = field(default_factory=list)  # MTD totals
    days: list[DailyAmount] = field(default_factory=list)


@dataclass
class UsageCostResponse:
    """Top-level parse result from the /cost endpoint."""

    models: list[ModelCost] = field(default_factory=list)  # MTD totals
    days: list[DailyCost] = field(default_factory=list)


# ------------------------------------------------------------------
# Data models — merged (UI-ready)
# ------------------------------------------------------------------


@dataclass
class ModelUsage:
    """Merged token + cost summary for a single model (used in UI / reports)."""

    model: str  # raw model id
    display_name: str  # "Flash" / "Pro" / …
    request_count: int = 0
    total_tokens: int = 0  # cache_hit + cache_miss + response
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    response_tokens: int = 0
    total_cost: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Cache-hit rate as a float in [0, 1]."""
        total = self.cache_hit_tokens + self.cache_miss_tokens
        if total <= 0:
            return 0.0
        return self.cache_hit_tokens / total


@dataclass
class MonthlyUsage:
    """Month-to-date, fully merged usage snapshot — the canonical output."""

    month: int
    year: int
    total_cost: float = 0.0
    models: dict = field(default_factory=dict)  # key → ModelUsage
    daily: list = field(default_factory=list)  # list of daily dicts (see below)

    # Each daily entry has shape:
    # {
    #     "date": "2026-06-16",
    #     "models": {
    #         "flash": ModelUsage(...),
    #         "pro":   ModelUsage(...),
    #         ...
    #     },
    # }


# ------------------------------------------------------------------
# Exception
# ------------------------------------------------------------------


class UsageAPIError(Exception):
    """Raised when a usage API call fails (network, HTTP, parse)."""


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------


class UsageAPI:
    """Client for the DeepSeek platform internal usage APIs.

    These endpoints require a **web-login Bearer token** obtained from
    ``localStorage.userToken`` on platform.deepseek.com — *not* the
    API key used for ``/user/balance``.
    """

    def __init__(self, usage_token: str, timeout: float = 15.0):
        self._token = usage_token
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {usage_token}",
                "x-app-version": "2.0.0",
                "Accept": "*/*",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                ),
            }
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_amount(self, month: int, year: int) -> UsageAmountResponse:
        """Fetch token-usage data for *month* / *year*."""
        url = PLATFORM_AMOUNT_URL.format(month=month, year=year)
        data = self._get_json(url)
        return self._parse_amount(data)

    def get_cost(self, month: int, year: int) -> UsageCostResponse:
        """Fetch cost data for *month* / *year*."""
        url = PLATFORM_COST_URL.format(month=month, year=year)
        data = self._get_json(url)
        return self._parse_cost(data)

    def get_monthly_usage(
        self, month: Optional[int] = None, year: Optional[int] = None
    ) -> MonthlyUsage:
        """Fetch both amount and cost, returning a merged ``MonthlyUsage``.

        If *month* / *year* are omitted the current calendar month is used.
        """
        if month is None or year is None:
            now = datetime.now()
            month = month if month is not None else now.month
            year = year if year is not None else now.year

        amount = self.get_amount(month, year)
        cost = self.get_cost(month, year)
        return self._merge(amount, cost, month, year)

    # ------------------------------------------------------------------
    # Internal: HTTP
    # ------------------------------------------------------------------

    def _get_json(self, url: str) -> dict:
        """GET *url* and return the parsed JSON body.

        Raises ``UsageAPIError`` on any failure.
        """
        try:
            resp = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as e:
            raise UsageAPIError(f"Network error: {e}") from e

        if resp.status_code != 200:
            hint = ""
            if resp.status_code == 401:
                hint = " — usage token may be invalid or expired"
            elif resp.status_code == 429:
                hint = " — rate limited, try again later"
            raise UsageAPIError(
                f"API returned HTTP {resp.status_code}{hint}: "
                f"{resp.text[:200]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            raise UsageAPIError(f"Invalid JSON response: {e}") from e

    # ------------------------------------------------------------------
    # Static parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_amount(data: dict) -> UsageAmountResponse:
        """Parse the /amount endpoint response."""
        try:
            biz = data["data"]["biz_data"]  # { total: [...], days: [...] }
        except (KeyError, TypeError) as e:
            raise UsageAPIError(
                f"Unexpected /amount response structure: {e}"
            ) from e

        models = UsageAPI._parse_model_list(biz.get("total", []), amount_mode=True)
        days = []
        for day_entry in biz.get("days", []):
            try:
                day_models = UsageAPI._parse_model_list(
                    day_entry.get("data", []), amount_mode=True
                )
            except Exception as e:
                raise UsageAPIError(
                    f"Failed to parse daily amount for {day_entry.get('date', '?')}: {e}"
                ) from e
            days.append(
                DailyAmount(date=day_entry.get("date", ""), models=day_models)
            )

        return UsageAmountResponse(models=models, days=days)

    @staticmethod
    def _parse_cost(data: dict) -> UsageCostResponse:
        """Parse the /cost endpoint response.

        The cost endpoint wraps ``biz_data`` in an **array** with a single
        element ``[{total: ..., days: ...}]``, unlike the amount endpoint
        which returns a plain object.  We handle both shapes defensively.
        """
        try:
            biz_raw = data["data"]["biz_data"]
        except (KeyError, TypeError) as e:
            raise UsageAPIError(
                f"Unexpected /cost response structure: {e}"
            ) from e

        # Normalise: if biz_data is a list, unwrap the first element
        if isinstance(biz_raw, list):
            if not biz_raw:
                raise UsageAPIError("Empty biz_data array in /cost response")
            biz = biz_raw[0]
        else:
            biz = biz_raw

        models = UsageAPI._parse_model_list(
            biz.get("total", []), amount_mode=False
        )
        days = []
        for day_entry in biz.get("days", []):
            try:
                day_models = UsageAPI._parse_model_list(
                    day_entry.get("data", []), amount_mode=False
                )
            except Exception as e:
                raise UsageAPIError(
                    f"Failed to parse daily cost for "
                    f"{day_entry.get('date', '?')}: {e}"
                ) from e
            days.append(
                DailyCost(date=day_entry.get("date", ""), models=day_models)
            )

        return UsageCostResponse(models=models, days=days)

    @staticmethod
    def _parse_model_list(
        items: list, *, amount_mode: bool
    ) -> list:
        """Parse a list of model-usage dicts into ``ModelAmount`` or ``ModelCost``.

        When *amount_mode* is True the return type is ``list[ModelAmount]``;
        otherwise ``list[ModelCost]``.
        """
        result = []
        for item in items:
            model_name = item.get("model", "unknown")
            if amount_mode:
                ma = ModelAmount(model=model_name)
                for entry in item.get("usage", []):
                    typ = entry.get("type", "")
                    val = int(entry.get("amount", 0))
                    if typ == "REQUEST":
                        ma.request_count = val
                    elif typ == "PROMPT_CACHE_HIT_TOKEN":
                        ma.cache_hit_tokens = val
                    elif typ == "PROMPT_CACHE_MISS_TOKEN":
                        ma.cache_miss_tokens = val
                    elif typ == "PROMPT_TOKEN":
                        ma.prompt_tokens = val
                    elif typ == "RESPONSE_TOKEN":
                        ma.response_tokens = val
                result.append(ma)
            else:
                mc = ModelCost(model=model_name)
                for entry in item.get("usage", []):
                    typ = entry.get("type", "")
                    val = float(entry.get("amount", 0))
                    if typ == "PROMPT_CACHE_HIT_TOKEN":
                        mc.cache_hit_cost = val
                    elif typ == "PROMPT_CACHE_MISS_TOKEN":
                        mc.cache_miss_cost = val
                    elif typ == "RESPONSE_TOKEN":
                        mc.response_cost = val
                result.append(mc)
        return result

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge(
        amount: UsageAmountResponse,
        cost: UsageCostResponse,
        month: int,
        year: int,
    ) -> MonthlyUsage:
        """Combine amount and cost data into a ``MonthlyUsage`` snapshot."""

        # --- Build a lookup: date → (model_key → ModelCost) ----------
        cost_by_date: dict[str, dict[str, ModelCost]] = {}
        for dc in cost.days:
            cmap: dict[str, ModelCost] = {}
            for mc in dc.models:
                cmap[_model_key(mc.model)] = mc
            if dc.date:
                cost_by_date[dc.date] = cmap

        # --- Build MTD model totals -----------------------------------
        # Amount-side totals (primary key set)
        amount_by_key: dict[str, ModelAmount] = {}
        for ma in amount.models:
            amount_by_key[_model_key(ma.model)] = ma

        # Cost-side totals
        cost_by_key: dict[str, ModelCost] = {}
        for mc in cost.models:
            cost_by_key[_model_key(mc.model)] = mc

        models: dict[str, ModelUsage] = {}
        for key, ma in amount_by_key.items():
            mc = cost_by_key.get(key)
            total_tokens = (
                ma.cache_hit_tokens + ma.cache_miss_tokens + ma.response_tokens
            )
            total_cost = round(
                (mc.cache_hit_cost + mc.cache_miss_cost + mc.response_cost)
                if mc
                else 0.0,
                6,
            )
            models[key] = ModelUsage(
                model=ma.model,
                display_name=_display_name(ma.model),
                request_count=ma.request_count,
                total_tokens=total_tokens,
                cache_hit_tokens=ma.cache_hit_tokens,
                cache_miss_tokens=ma.cache_miss_tokens,
                response_tokens=ma.response_tokens,
                total_cost=total_cost,
            )

        # --- Build daily list -----------------------------------------
        daily: list[dict] = []
        for da in amount.days:
            day_models: dict[str, ModelUsage] = {}
            dc_lookup = cost_by_date.get(da.date, {})
            for ma in da.models:
                key = _model_key(ma.model)
                mc = dc_lookup.get(key)
                total_tokens = (
                    ma.cache_hit_tokens
                    + ma.cache_miss_tokens
                    + ma.response_tokens
                )
                total_cost = round(
                    (mc.cache_hit_cost + mc.cache_miss_cost + mc.response_cost)
                    if mc
                    else 0.0,
                    6,
                )
                day_models[key] = ModelUsage(
                    model=ma.model,
                    display_name=_display_name(ma.model),
                    request_count=ma.request_count,
                    total_tokens=total_tokens,
                    cache_hit_tokens=ma.cache_hit_tokens,
                    cache_miss_tokens=ma.cache_miss_tokens,
                    response_tokens=ma.response_tokens,
                    total_cost=total_cost,
                )
            daily.append({"date": da.date, "models": day_models})

        # --- Sum total cost -------------------------------------------
        total_cost = round(sum(m.total_cost for m in models.values()), 6)

        return MonthlyUsage(
            month=month,
            year=year,
            total_cost=total_cost,
            models=models,
            daily=daily,
        )
