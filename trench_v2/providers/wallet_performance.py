"""Wallet-performance providers used by Best Signals."""

from __future__ import annotations

from typing import Protocol

import httpx

from trench_v2.core.models import Chain
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError
from wallet_performance import WalletPerformanceCandidate


class MoralisJsonClient(Protocol):
    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict | list:
        """Return JSON from Moralis."""


_CHAIN_QUERY = {
    Chain.ETHEREUM: "eth",
    Chain.BASE: "base",
    Chain.BSC: "bsc",
}

_PERIOD_DAYS = {
    "week": "7",
    "month": "30",
    "year": "all",
}


class MoralisTopTradersProvider:
    """Fetch profitable wallets for a token using Moralis top-gainers data."""

    def __init__(self, api_key: str, client: MoralisJsonClient | None = None):
        self.client = client or AsyncJsonClient(
            "moralis-top-traders",
            headers={"X-API-Key": api_key},
        )

    async def best_wallets_for_token(
        self,
        *,
        chain: Chain,
        token_address: str,
        token_symbol: str,
        periods: tuple[str, ...],
    ) -> list[WalletPerformanceCandidate]:
        chain_query = _CHAIN_QUERY.get(chain)
        if not chain_query:
            return []

        candidates: list[WalletPerformanceCandidate] = []
        for period in periods:
            days = _PERIOD_DAYS.get(period)
            if days is None:
                continue
            try:
                data = await self.client.get_json(
                    f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/top-gainers",
                    params={"chain": chain_query, "days": days},
                )
            except ProviderRateLimitError:
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 404, 422}:
                    continue
                raise
            if not isinstance(data, dict):
                continue
            rows = data.get("result")
            if not isinstance(rows, list) or not rows:
                continue
            for row in rows[:5]:
                candidate = _candidate_from_row(
                    row,
                    chain=chain_query,
                    period=period,
                    token_symbol=token_symbol,
                )
                if candidate:
                    candidates.append(candidate)
        return candidates


def _candidate_from_row(
    row: object,
    *,
    chain: str,
    period: str,
    token_symbol: str,
) -> WalletPerformanceCandidate | None:
    if not isinstance(row, dict):
        return None
    wallet = str(row.get("address") or "").strip()
    trades = _int_or_zero(row.get("count_of_trades"))
    realized_pnl_usd = _float_or_zero(row.get("realized_profit_usd"))
    roi_pct = _float_or_zero(row.get("realized_profit_percentage"))
    if not wallet:
        return None
    return WalletPerformanceCandidate(
        chain=chain,
        wallet_address=wallet,
        period=period,
        realized_pnl_usd=realized_pnl_usd,
        roi_pct=roi_pct,
        win_rate=1.0,
        trades=trades,
        wins=trades,
        losses=0,
        top_tokens=(token_symbol,) if token_symbol else (),
        evidence_url="https://docs.moralis.com/data-api/evm/token/signals/top-traders",
    )


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
