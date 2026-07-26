"""Market-data providers for command scans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from trench_v2.core.models import Chain, RiskLevel, RiskReport, TokenScan
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


class DexJsonClient(Protocol):
    async def get_json(self, url: str) -> dict | list:
        """Return JSON from DexScreener."""


class DexScreenerMarketDataProvider:
    """Fetch normalized token market data from DexScreener."""

    _CHAIN_IDS = {
        "solana": Chain.SOLANA,
        "ethereum": Chain.ETHEREUM,
        "base": Chain.BASE,
        "bsc": Chain.BSC,
        "robinhood": Chain.ROBINHOOD,
    }

    def __init__(self, client: DexJsonClient | None = None):
        self.client = client or AsyncJsonClient("dexscreener-market")

    async def fetch_token(self, chain: Chain, address: str) -> TokenScan:
        try:
            data = await self.client.get_json(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
        except ProviderRateLimitError:
            return self._unknown(chain, address, "DexScreener rate limited")
        except Exception as exc:
            return self._unknown(chain, address, f"DexScreener unavailable: {exc}")

        if not isinstance(data, dict):
            return self._unknown(chain, address, "DexScreener returned unexpected payload")

        pairs = data.get("pairs")
        if not isinstance(pairs, list):
            return self._unknown(chain, address, "no DexScreener pair found")
        if not pairs:
            return self._unknown(chain, address, "no DexScreener pair found")

        matching_pairs = [
            pair
            for pair in pairs
            if (
                isinstance(pair, dict)
                and self._chain_from_pair(pair) is chain
                and self._base_token_matches(pair, chain, address)
            )
        ]
        if not matching_pairs:
            return self._unknown(
                chain,
                address,
                "no DexScreener base-token pair found for requested chain",
            )

        pair = max(matching_pairs, key=lambda item: _float_or_none((item.get("liquidity") or {}).get("usd")) or 0)
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        labels = pair.get("labels") if isinstance(pair.get("labels"), list) else []
        url = _str_or_none(pair.get("url"))
        return TokenScan(
            chain=chain,
            address=str(base_token.get("address") or address),
            symbol=str(base_token.get("symbol") or "UNKNOWN"),
            name=str(base_token.get("name") or "Unknown Token"),
            market_cap_usd=_float_or_none(pair.get("marketCap") or pair.get("fdv")),
            liquidity_usd=_float_or_none((pair.get("liquidity") or {}).get("usd")),
            created_at=_datetime_from_ms(pair.get("pairCreatedAt")),
            pool_type=_pool_type(pair.get("dexId"), labels),
            source_urls=[url] if url else [],
        )

    def _chain_from_pair(self, pair: dict) -> Chain | None:
        return self._CHAIN_IDS.get(str(pair.get("chainId", "")).lower())

    def _base_token_matches(self, pair: dict, chain: Chain, address: str) -> bool:
        base_token = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        candidate = str(base_token.get("address") or "").strip()
        if chain is Chain.SOLANA:
            return candidate == address
        return candidate.lower() == address.lower()

    def _unknown(self, chain: Chain, address: str, reason: str) -> TokenScan:
        return TokenScan(
            chain=chain,
            address=address,
            symbol="UNKNOWN",
            name="Unknown Token",
            risk=RiskReport(level=RiskLevel.MEDIUM, reasons=[reason]),
        )


def _str_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime_from_ms(value: object) -> datetime | None:
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)


def _pool_type(dex_id: object, labels: list[object]) -> str | None:
    text = " ".join(str(value).lower() for value in [dex_id, *labels])
    if "v4" in text:
        return "V4"
    if "v3" in text:
        return "V3"
    if "v2" in text:
        return "V2"
    if "uniswap" in text:
        return "V2/V3"
    if "pancake" in text:
        return "V2"
    return None
