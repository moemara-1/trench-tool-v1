"""DexScreener-backed discovery for free/cheap V2 live signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote_plus

from trench_v2.core.models import Chain
from trench_v2.providers.http import AsyncJsonClient


class JsonClient(Protocol):
    async def get_json(self, url: str) -> dict | list:
        """Return object or list JSON from a GET request."""


@dataclass(frozen=True, slots=True)
class DexTokenProfile:
    chain: Chain
    address: str
    url: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DexPair:
    chain: Chain
    token_address: str
    symbol: str
    name: str
    url: str | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    buys_5m: int
    buys_1h: int
    buys_24h: int
    pair_created_at: datetime | None
    sells_5m: int = 0
    sells_1h: int = 0
    sells_24h: int = 0
    price_change_5m: float | None = None
    price_change_1h: float | None = None
    price_change_24h: float | None = None


class DexScreenerProvider:
    """Fetch latest token profiles and pair details from DexScreener."""

    _DISCOVERY_URLS = (
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-boosts/top/v1",
    )
    _SEARCH_QUERIES = ("eth", "uniswap", "bsc", "pancakeswap")
    _GECKO_NETWORKS = {
        "eth": Chain.ETHEREUM,
        "bsc": Chain.BSC,
        "base": Chain.BASE,
    }

    _CHAIN_IDS = {
        "solana": Chain.SOLANA,
        "ethereum": Chain.ETHEREUM,
        "base": Chain.BASE,
        "bsc": Chain.BSC,
    }

    def __init__(self, client: JsonClient | None = None, gecko_client: JsonClient | None = None):
        self.client = client or AsyncJsonClient("dexscreener")
        self.gecko_client = gecko_client or client or AsyncJsonClient(
            "geckoterminal",
            headers={
                "Accept": "application/json",
                "User-Agent": "trench-tool/2.0",
            },
        )

    async def latest_profiles(self) -> list[DexTokenProfile]:
        seen: set[tuple[Chain, str]] = set()
        profiles: list[DexTokenProfile] = []
        for url in self._DISCOVERY_URLS:
            data = await self.client.get_json(url)
            if not isinstance(data, list):
                continue

            for item in data:
                profile = self._profile_from_json(item)
                if not profile:
                    continue
                key = (profile.chain, profile.address.lower())
                if key in seen:
                    continue
                seen.add(key)
                profiles.append(profile)
        return profiles

    def _profile_from_json(self, item: object) -> DexTokenProfile | None:
        if not isinstance(item, dict):
            return None
        chain = self._CHAIN_IDS.get(str(item.get("chainId", "")).lower())
        address = str(item.get("tokenAddress") or "").strip()
        if not chain or not address:
            return None
        return DexTokenProfile(
            chain=chain,
            address=address,
            url=_str_or_none(item.get("url")),
            description=_str_or_none(item.get("description")),
        )

    async def best_pair(self, profile: DexTokenProfile) -> DexPair | None:
        data = await self.client.get_json(f"https://api.dexscreener.com/latest/dex/tokens/{profile.address}")
        if not isinstance(data, dict):
            return None
        pairs = data.get("pairs")
        if not isinstance(pairs, list):
            return None

        normalized = [
            pair
            for pair in (self._pair_from_json(profile, item) for item in pairs)
            if pair is not None and pair.chain is profile.chain
        ]
        if not normalized:
            return None
        return max(normalized, key=lambda pair: pair.liquidity_usd or 0)

    async def latest_pairs(self) -> list[DexPair]:
        """Return direct pair candidates from real discovery feeds."""
        seen: set[tuple[Chain, str]] = set()
        pairs: list[DexPair] = []

        for query in self._SEARCH_QUERIES:
            url = f"https://api.dexscreener.com/latest/dex/search?q={quote_plus(query)}"
            try:
                data = await self.client.get_json(url)
            except Exception:
                continue
            if not isinstance(data, dict) or not isinstance(data.get("pairs"), list):
                continue
            for item in data["pairs"]:
                profile = self._profile_from_search_pair(item)
                if not profile:
                    continue
                pair = self._pair_from_json(profile, item)
                if pair:
                    _append_unique_pair(pairs, seen, pair)

        for network, chain in self._GECKO_NETWORKS.items():
            url = f"https://api.geckoterminal.com/api/v2/networks/{network}/new_pools"
            try:
                data = await self.gecko_client.get_json(url)
            except Exception:
                continue
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                continue
            for row in rows:
                pair = self._gecko_pair_from_json(chain, network, row)
                if pair:
                    _append_unique_pair(pairs, seen, pair)

        return pairs

    def _pair_from_json(self, profile: DexTokenProfile, item: object) -> DexPair | None:
        if not isinstance(item, dict):
            return None
        chain = self._CHAIN_IDS.get(str(item.get("chainId", "")).lower())
        base_token = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
        address = str(base_token.get("address") or profile.address)
        return DexPair(
            chain=chain or profile.chain,
            token_address=address,
            symbol=str(base_token.get("symbol") or "UNKNOWN"),
            name=str(base_token.get("name") or "Unknown Token"),
            url=_str_or_none(item.get("url")) or profile.url,
            market_cap_usd=_float_or_none(item.get("marketCap") or item.get("fdv")),
            liquidity_usd=_float_or_none((item.get("liquidity") or {}).get("usd")),
            volume_24h_usd=_float_or_none((item.get("volume") or {}).get("h24")),
            buys_5m=_int_or_zero(((item.get("txns") or {}).get("m5") or {}).get("buys")),
            buys_1h=_int_or_zero(((item.get("txns") or {}).get("h1") or {}).get("buys")),
            buys_24h=_int_or_zero(((item.get("txns") or {}).get("h24") or {}).get("buys")),
            pair_created_at=_datetime_from_ms(item.get("pairCreatedAt")),
            sells_5m=_int_or_zero(((item.get("txns") or {}).get("m5") or {}).get("sells")),
            sells_1h=_int_or_zero(((item.get("txns") or {}).get("h1") or {}).get("sells")),
            sells_24h=_int_or_zero(((item.get("txns") or {}).get("h24") or {}).get("sells")),
            price_change_5m=_float_or_none((item.get("priceChange") or {}).get("m5")),
            price_change_1h=_float_or_none((item.get("priceChange") or {}).get("h1")),
            price_change_24h=_float_or_none((item.get("priceChange") or {}).get("h24")),
        )

    def _profile_from_search_pair(self, item: object) -> DexTokenProfile | None:
        if not isinstance(item, dict):
            return None
        chain = self._CHAIN_IDS.get(str(item.get("chainId", "")).lower())
        base_token = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
        address = str(base_token.get("address") or "").strip()
        if not chain or not address:
            return None
        return DexTokenProfile(
            chain=chain,
            address=address,
            url=_str_or_none(item.get("url")),
        )

    def _gecko_pair_from_json(self, chain: Chain, network: str, row: object) -> DexPair | None:
        if not isinstance(row, dict):
            return None
        attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
        relationships = row.get("relationships") if isinstance(row.get("relationships"), dict) else {}
        base_token = relationships.get("base_token") if isinstance(relationships.get("base_token"), dict) else {}
        base_data = base_token.get("data") if isinstance(base_token.get("data"), dict) else {}
        token_address = _token_address_from_gecko_id(base_data.get("id"))
        if not token_address:
            return None

        name = str(attributes.get("name") or "Unknown Token")
        symbol = name.split("/", 1)[0].strip() or "UNKNOWN"
        pool_address = _str_or_none(attributes.get("address"))
        volume = attributes.get("volume_usd") if isinstance(attributes.get("volume_usd"), dict) else {}
        transactions = attributes.get("transactions") if isinstance(attributes.get("transactions"), dict) else {}
        return DexPair(
            chain=chain,
            token_address=token_address,
            symbol=symbol,
            name=name,
            url=f"https://www.geckoterminal.com/{network}/pools/{pool_address}" if pool_address else None,
            market_cap_usd=_float_or_none(attributes.get("market_cap_usd") or attributes.get("fdv_usd")),
            liquidity_usd=_float_or_none(attributes.get("reserve_in_usd")),
            volume_24h_usd=_float_or_none(volume.get("h24")),
            buys_5m=_int_or_zero(_nested_value(transactions, "m5", "buys")),
            buys_1h=_int_or_zero(_nested_value(transactions, "h1", "buys")),
            buys_24h=_int_or_zero(_nested_value(transactions, "h24", "buys")),
            pair_created_at=_datetime_from_iso(attributes.get("pool_created_at")),
            sells_5m=_int_or_zero(_nested_value(transactions, "m5", "sells")),
            sells_1h=_int_or_zero(_nested_value(transactions, "h1", "sells")),
            sells_24h=_int_or_zero(_nested_value(transactions, "h24", "sells")),
            price_change_5m=_float_or_none(_nested_value(attributes, "price_change_percentage", "m5")),
            price_change_1h=_float_or_none(_nested_value(attributes, "price_change_percentage", "h1")),
            price_change_24h=_float_or_none(_nested_value(attributes, "price_change_percentage", "h24")),
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


def _int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _datetime_from_ms(value: object) -> datetime | None:
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)


def _datetime_from_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _nested_value(data: dict, first: str, second: str) -> object:
    nested = data.get(first)
    if not isinstance(nested, dict):
        return None
    return nested.get(second)


def _token_address_from_gecko_id(value: object) -> str | None:
    if not isinstance(value, str) or "_" not in value:
        return None
    return value.split("_", 1)[1].strip() or None


def _append_unique_pair(pairs: list[DexPair], seen: set[tuple[Chain, str]], pair: DexPair) -> None:
    key = (pair.chain, pair.token_address.lower())
    if key in seen:
        return
    seen.add(key)
    pairs.append(pair)
