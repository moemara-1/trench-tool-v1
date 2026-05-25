from datetime import datetime, timezone

import pytest

from trench_v2.chains.adapters import ChainAdapterRegistry
from trench_v2.core.models import Chain
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


def test_chain_registry_uses_hint_for_ambiguous_evm_addresses():
    chain = ChainAdapterRegistry().resolve(
        "0x1111111111111111111111111111111111111111",
        hint="base",
    )

    assert chain is Chain.BASE


def test_chain_registry_infers_solana_addresses():
    chain = ChainAdapterRegistry().resolve("So11111111111111111111111111111111111111112")

    assert chain is Chain.SOLANA


@pytest.mark.asyncio
async def test_http_client_refuses_calls_while_provider_circuit_is_open():
    client = AsyncJsonClient(name="helius")
    client.breaker.record_rate_limit("HTTP 429")

    with pytest.raises(ProviderRateLimitError):
        await client.get_json("https://example.invalid")

    assert client.breaker.cooldown_until is not None
    assert client.breaker.cooldown_until > datetime.now(timezone.utc)
