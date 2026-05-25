"""Provider health probes for configured RPC endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from trench_v2.config import V2Settings
from trench_v2.core.models import Chain, ProviderHealth
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


class JsonRpcClient(Protocol):
    async def post_json(self, url: str, payload: dict) -> dict:
        """POST a JSON-RPC payload and return object JSON."""


@dataclass(slots=True)
class JsonRpcHealthChecker:
    client: JsonRpcClient

    async def check_solana(self, url: str) -> ProviderHealth:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "processed"}],
        }
        return await self._check("sol-rpc", url, payload)

    async def check_solana_pool(self, urls: tuple[str, ...]) -> ProviderHealth:
        attempts: list[ProviderHealth] = []
        for index, url in enumerate(urls, start=1):
            health = await self.check_solana(url)
            if health.ok:
                return ProviderHealth(
                    name="sol-rpc",
                    ok=True,
                    detail=f"{index}/{len(urls)} endpoint ok",
                    checked_at=datetime.now(timezone.utc),
                )
            attempts.append(health)

        rate_limited = bool(attempts) and all(health.rate_limited for health in attempts)
        details = {health.detail or "failed" for health in attempts}
        return ProviderHealth(
            name="sol-rpc",
            ok=False,
            rate_limited=rate_limited,
            detail="all endpoints rate limited" if rate_limited else ", ".join(sorted(details)),
            checked_at=datetime.now(timezone.utc),
        )

    async def check_evm(self, chain: Chain, url: str, expected_chain_id: str) -> ProviderHealth:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
        health, data = await self._check_with_data(f"{chain.value}-rpc", url, payload)
        if not health.ok:
            return health

        actual_chain_id = str(data.get("result", "")).lower()
        if actual_chain_id != expected_chain_id.lower():
            return ProviderHealth(
                name=f"{chain.value}-rpc",
                ok=False,
                detail=f"unexpected chain id {actual_chain_id or 'missing'}",
                checked_at=datetime.now(timezone.utc),
            )
        return health

    async def _check(self, name: str, url: str, payload: dict) -> ProviderHealth:
        health, _data = await self._check_with_data(name, url, payload)
        return health

    async def _check_with_data(self, name: str, url: str, payload: dict) -> tuple[ProviderHealth, dict]:
        try:
            data = await self.client.post_json(url, payload)
        except ProviderRateLimitError:
            return (
                ProviderHealth(
                    name=name,
                    ok=False,
                    rate_limited=True,
                    detail="HTTP 429",
                    checked_at=datetime.now(timezone.utc),
                ),
                {},
            )
        except Exception as exc:
            return (
                ProviderHealth(
                    name=name,
                    ok=False,
                    detail=type(exc).__name__,
                    checked_at=datetime.now(timezone.utc),
                ),
                {},
            )

        if data.get("error"):
            return (
                ProviderHealth(
                    name=name,
                    ok=False,
                    detail="json-rpc error",
                    checked_at=datetime.now(timezone.utc),
                ),
                data,
            )

        return ProviderHealth(name=name, ok=True, checked_at=datetime.now(timezone.utc)), data


class ProviderHealthService:
    """Build provider health from current V2 settings."""

    _EVM_CHAIN_IDS = {
        Chain.ETHEREUM: "0x1",
        Chain.BASE: "0x2105",
        Chain.BSC: "0x38",
    }

    def __init__(
        self,
        settings: V2Settings,
        checker: JsonRpcHealthChecker | None = None,
    ):
        self.settings = settings
        self.checker = checker or JsonRpcHealthChecker(AsyncJsonClient("provider-health"))

    async def check(self) -> list[ProviderHealth]:
        tasks = []

        solana_urls = self.settings.rpc_urls_for(Chain.SOLANA)
        if self.settings.solana_provider_health_enabled and solana_urls:
            tasks.append(self.checker.check_solana_pool(solana_urls))

        for chain, expected_chain_id in self._EVM_CHAIN_IDS.items():
            rpc_url = self.settings.rpc_url_for(chain)
            if rpc_url:
                tasks.append(self.checker.check_evm(chain, rpc_url, expected_chain_id))

        if not tasks:
            return [ProviderHealth(name="v2-null-provider", ok=True, detail="no provider env configured")]

        return list(await asyncio.gather(*tasks))
