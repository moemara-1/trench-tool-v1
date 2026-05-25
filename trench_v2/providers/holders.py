"""Holder providers for supply distribution and bundle analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trench_v2.core.models import Chain, HolderCluster
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


class MoralisJsonClient(Protocol):
    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict | list:
        """Return JSON from Moralis."""


_MORALIS_CHAIN_IDS = {
    Chain.ETHEREUM: "eth",
    Chain.BASE: "base",
    Chain.BSC: "bsc",
}


@dataclass(frozen=True, slots=True)
class MoralisTokenOwner:
    owner_address: str
    balance_formatted: float | None
    supply_percent: float
    is_contract: bool
    label: str | None = None
    entity: str | None = None
    usd_value: float | None = None


class MoralisTokenOwnersProvider:
    """Fetch ERC-20 owner snapshots from Moralis Token API."""

    def __init__(self, api_key: str, client: MoralisJsonClient | None = None):
        self.client = client or AsyncJsonClient(
            "moralis-token-owners",
            headers={"accept": "application/json", "X-API-Key": api_key},
        )

    async def fetch_owners(
        self,
        chain: Chain,
        token_address: str,
        *,
        limit: int = 50,
    ) -> list[MoralisTokenOwner]:
        chain_id = _MORALIS_CHAIN_IDS.get(chain)
        if not chain_id:
            return []

        try:
            data = await self.client.get_json(
                f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/owners",
                params={"chain": chain_id, "limit": str(limit)},
            )
        except ProviderRateLimitError:
            return []
        except Exception:
            return []

        if not isinstance(data, dict):
            return []
        result = data.get("result")
        if not isinstance(result, list):
            return []
        return [_owner_from_json(item) for item in result if isinstance(item, dict)]


class MoralisHolderClusterProvider:
    """Build conservative holder clusters from Moralis owner rows."""

    min_cluster_supply_percent = 1.0

    def __init__(self, owners_provider: MoralisTokenOwnersProvider):
        self.owners_provider = owners_provider

    async def fetch_holder_clusters(self, chain: Chain, address: str) -> list[HolderCluster]:
        owners = await self.owners_provider.fetch_owners(chain, address)
        clusters: list[HolderCluster] = []
        for owner in owners:
            if owner.supply_percent < self.min_cluster_supply_percent:
                continue
            evidence = ["Moralis token owners"]
            if owner.entity:
                evidence.append(owner.entity)
            elif owner.label:
                evidence.append(owner.label)
            clusters.append(
                HolderCluster(
                    label=_cluster_label(owner),
                    wallets=[owner.owner_address],
                    supply_percent=round(owner.supply_percent, 4),
                    evidence=evidence,
                )
            )
        return clusters


def _owner_from_json(item: dict) -> MoralisTokenOwner:
    return MoralisTokenOwner(
        owner_address=str(item.get("owner_address") or "").lower(),
        balance_formatted=_float_or_none(item.get("balance_formatted")),
        supply_percent=_float_or_none(item.get("percentage_relative_to_total_supply")) or 0.0,
        is_contract=bool(item.get("is_contract")),
        label=_str_or_none(item.get("owner_address_label")),
        entity=_str_or_none(item.get("entity")),
        usd_value=_float_or_none(item.get("usd_value")),
    )


def _cluster_label(owner: MoralisTokenOwner) -> str:
    text = " ".join(part.lower() for part in [owner.label or "", owner.entity or ""])
    if owner.is_contract:
        return "contract_holder"
    if any(word in text for word in ["team", "dev", "creator", "deployer", "owner"]):
        return "team"
    if any(word in text for word in ["sniper", "snipe"]):
        return "sniper"
    return "large_holder"


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None

