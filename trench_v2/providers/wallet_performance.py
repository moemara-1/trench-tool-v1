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

_RECENT_BUY_LIMIT = "25"
_MAX_RECENT_WALLET_CHECKS = 6
_MIN_RECENT_BUY_USD = 250.0


class MoralisTopTradersProvider:
    """Fetch profitable wallets for a token using Moralis wallet PnL evidence."""

    def __init__(self, api_key: str, client: MoralisJsonClient | None = None):
        self.client = client or AsyncJsonClient(
            "moralis-top-traders",
            headers={"X-API-Key": api_key},
        )
        self._wallet_summary_cache: dict[tuple[str, str, str], WalletPerformanceCandidate | None] = {}

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

        normalized_periods = tuple(
            period.lower().strip()
            for period in periods
            if period.lower().strip() in _PERIOD_DAYS
        )
        candidates: list[WalletPerformanceCandidate] = []
        for period in normalized_periods:
            days = _PERIOD_DAYS[period]
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
                candidate = _candidate_from_top_gainer_row(
                    row,
                    chain=chain_query,
                    period=period,
                    token_symbol=token_symbol,
                )
                if candidate:
                    candidates.append(candidate)

        missing_periods = _periods_without_confluence(candidates, normalized_periods)
        if missing_periods:
            candidates.extend(
                await self._recent_profitable_buyers_for_token(
                    chain=chain_query,
                    token_address=token_address,
                    token_symbol=token_symbol,
                    periods=missing_periods,
                )
            )
        return _dedupe_candidates(candidates)

    async def _recent_profitable_buyers_for_token(
        self,
        *,
        chain: str,
        token_address: str,
        token_symbol: str,
        periods: tuple[str, ...],
    ) -> list[WalletPerformanceCandidate]:
        try:
            data = await self.client.get_json(
                f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/swaps",
                params={
                    "chain": chain,
                    "transactionTypes": "buy",
                    "order": "DESC",
                    "limit": _RECENT_BUY_LIMIT,
                },
            )
        except ProviderRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 404, 422}:
                return []
            raise
        rows = data.get("result") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            return []

        recent_buys = _recent_buy_wallets(rows, token_address=token_address)
        candidates: list[WalletPerformanceCandidate] = []
        for wallet, buy_usd in recent_buys[:_MAX_RECENT_WALLET_CHECKS]:
            for period in periods:
                candidate = await self._wallet_summary_candidate(
                    chain=chain,
                    wallet=wallet,
                    period=period,
                    token_symbol=token_symbol,
                    current_buy_usd=buy_usd,
                )
                if candidate:
                    candidates.append(candidate)
        return candidates

    async def _wallet_summary_candidate(
        self,
        *,
        chain: str,
        wallet: str,
        period: str,
        token_symbol: str,
        current_buy_usd: float,
    ) -> WalletPerformanceCandidate | None:
        days = _PERIOD_DAYS.get(period)
        if days is None:
            return None
        cache_key = (chain, wallet.lower(), period)
        if cache_key in self._wallet_summary_cache:
            cached = self._wallet_summary_cache[cache_key]
            if cached is None:
                return None
            return _with_current_buy(cached, current_buy_usd=current_buy_usd, token_symbol=token_symbol)

        try:
            data = await self.client.get_json(
                f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet}/profitability/summary",
                params={"chain": chain, "days": days},
            )
        except ProviderRateLimitError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 404, 422}:
                self._wallet_summary_cache[cache_key] = None
                return None
            raise
        candidate = _candidate_from_wallet_summary(
            data,
            chain=chain,
            wallet=wallet,
            period=period,
            token_symbol=token_symbol,
            current_buy_usd=current_buy_usd,
        )
        self._wallet_summary_cache[cache_key] = candidate
        return candidate


def _candidate_from_top_gainer_row(
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
        win_rate=None,
        trades=trades,
        wins=0,
        losses=0,
        top_tokens=(token_symbol,) if token_symbol else (),
        evidence_url="https://docs.moralis.com/data-api/evm/token/signals/top-traders",
    )


def _candidate_from_wallet_summary(
    data: object,
    *,
    chain: str,
    wallet: str,
    period: str,
    token_symbol: str,
    current_buy_usd: float,
) -> WalletPerformanceCandidate | None:
    if not isinstance(data, dict):
        return None
    trades = _int_or_zero(data.get("total_count_of_trades") or data.get("total_trades"))
    realized_pnl_usd = _float_or_zero(
        data.get("total_realized_profit_usd")
        or data.get("realized_profit_usd")
        or data.get("total_profit_usd")
    )
    roi_pct = _float_or_zero(
        data.get("total_realized_profit_percentage")
        or data.get("realized_profit_percentage")
        or data.get("total_roi_percentage")
    )
    if not wallet or trades <= 0 or realized_pnl_usd <= 0 or roi_pct <= 0:
        return None
    return WalletPerformanceCandidate(
        chain=chain,
        wallet_address=wallet,
        period=period,
        realized_pnl_usd=realized_pnl_usd,
        roi_pct=roi_pct,
        win_rate=None,
        trades=trades,
        wins=0,
        losses=0,
        top_tokens=(token_symbol,) if token_symbol else (),
        evidence_url="https://docs.moralis.com/web3-data-api/evm/reference/wallet-api",
        current_buy_usd=current_buy_usd,
    )


def _with_current_buy(
    candidate: WalletPerformanceCandidate,
    *,
    current_buy_usd: float,
    token_symbol: str,
) -> WalletPerformanceCandidate:
    return WalletPerformanceCandidate(
        chain=candidate.chain,
        wallet_address=candidate.wallet_address,
        period=candidate.period,
        realized_pnl_usd=candidate.realized_pnl_usd,
        roi_pct=candidate.roi_pct,
        win_rate=candidate.win_rate,
        trades=candidate.trades,
        wins=candidate.wins,
        losses=candidate.losses,
        top_tokens=(token_symbol,) if token_symbol else candidate.top_tokens,
        evidence_url=candidate.evidence_url,
        current_buy_usd=current_buy_usd,
    )


def _recent_buy_wallets(rows: list, *, token_address: str) -> list[tuple[str, float]]:
    seen: set[str] = set()
    wallets: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _row_is_token_buy(row, token_address=token_address):
            continue
        wallet = _wallet_from_swap_row(row)
        if not wallet:
            continue
        key = wallet.lower()
        if key in seen:
            continue
        buy_usd = _float_or_zero(
            row.get("totalValueUsd")
            or row.get("total_value_usd")
            or row.get("amountUsd")
            or row.get("value_usd")
        )
        if buy_usd < _MIN_RECENT_BUY_USD:
            continue
        seen.add(key)
        wallets.append((wallet, buy_usd))
    return wallets


def _row_is_token_buy(row: dict, *, token_address: str) -> bool:
    transaction_type = str(row.get("transactionType") or row.get("transaction_type") or "").lower()
    if transaction_type and transaction_type != "buy":
        return False
    bought = row.get("bought") if isinstance(row.get("bought"), dict) else {}
    bought_address = str(bought.get("address") or bought.get("tokenAddress") or "").lower()
    if bought_address:
        return bought_address == token_address.lower()
    return transaction_type == "buy"


def _wallet_from_swap_row(row: dict) -> str:
    return str(
        row.get("walletAddress")
        or row.get("wallet_address")
        or row.get("traderAddress")
        or row.get("trader_address")
        or row.get("maker")
        or row.get("address")
        or ""
    ).strip()


def _periods_without_confluence(
    candidates: list[WalletPerformanceCandidate],
    periods: tuple[str, ...],
) -> tuple[str, ...]:
    missing: list[str] = []
    for period in periods:
        count = sum(1 for candidate in candidates if candidate.period.lower().strip() == period)
        if count < 2:
            missing.append(period)
    return tuple(missing)


def _dedupe_candidates(candidates: list[WalletPerformanceCandidate]) -> list[WalletPerformanceCandidate]:
    deduped: dict[tuple[str, str], WalletPerformanceCandidate] = {}
    for candidate in candidates:
        key = (candidate.period.lower().strip(), candidate.wallet_address.lower())
        previous = deduped.get(key)
        if previous is None or _candidate_strength(candidate) > _candidate_strength(previous):
            deduped[key] = candidate
    return list(deduped.values())


def _candidate_strength(candidate: WalletPerformanceCandidate) -> tuple[float, float, int]:
    return (candidate.current_buy_usd or 0, candidate.realized_pnl_usd, candidate.trades)


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