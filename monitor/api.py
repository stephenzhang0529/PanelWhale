from dataclasses import dataclass
from typing import Optional

import requests


DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"


# Currency symbol mapping
_CURRENCY_MAP = {
    "CNY": "¥",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}


@dataclass
class BalanceInfo:
    is_available: bool
    total_balance: float
    granted_balance: float
    topped_up_balance: float
    currency: str = "CNY"

    @property
    def symbol(self) -> str:
        """Human-readable currency symbol, e.g. ¥ or $."""
        return _CURRENCY_MAP.get(self.currency, self.currency)


class APIError(Exception):
    """Raised when the DeepSeek API call fails."""


class DeepSeekAPI:
    def __init__(self, api_key: str, timeout: float = 10.0):
        self._api_key = api_key
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
        )

    def get_balance(self) -> BalanceInfo:
        """Fetch current balance from DeepSeek API.

        Raises APIError on any failure (network, HTTP error, unexpected response).
        """
        try:
            resp = self._session.get(
                DEEPSEEK_BALANCE_URL,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise APIError(f"Network error: {e}") from e

        if resp.status_code != 200:
            raise APIError(
                f"API returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise APIError(f"Invalid JSON response: {e}") from e

        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict) -> BalanceInfo:
        try:
            is_available = bool(data.get("is_available", False))
            infos = data.get("balance_infos", [])
            if not infos:
                raise APIError("No balance_infos in response")

            b = infos[0]
            return BalanceInfo(
                is_available=is_available,
                total_balance=float(b.get("total_balance", "0")),
                granted_balance=float(b.get("granted_balance", "0")),
                topped_up_balance=float(b.get("topped_up_balance", "0")),
                currency=b.get("currency", "CNY"),
            )
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise APIError(f"Failed to parse balance response: {e}") from e
