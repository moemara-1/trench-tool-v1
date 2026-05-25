import pytest

from trench_v2.config import V2Settings
from trench_v2.core.models import Chain
from trench_v2.providers.health import JsonRpcHealthChecker, ProviderHealthService
from trench_v2.providers.http import ProviderRateLimitError


class FakeRpcClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def post_json(self, url: str, payload: dict) -> dict:
        self.calls.append((url, payload))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_evm_health_checker_validates_expected_chain_id():
    client = FakeRpcClient({"https://eth.example": {"result": "0x1"}})
    checker = JsonRpcHealthChecker(client=client)

    health = await checker.check_evm(Chain.ETHEREUM, "https://eth.example", expected_chain_id="0x1")

    assert health.ok is True
    assert health.name == "eth-rpc"
    assert client.calls[0][1]["method"] == "eth_chainId"


@pytest.mark.asyncio
async def test_health_checker_marks_rate_limited_provider():
    client = FakeRpcClient({"https://sol.example": ProviderRateLimitError("HTTP 429")})
    checker = JsonRpcHealthChecker(client=client)

    health = await checker.check_solana("https://sol.example")

    assert health.ok is False
    assert health.rate_limited is True
    assert health.detail == "HTTP 429"


@pytest.mark.asyncio
async def test_solana_pool_health_passes_when_later_endpoint_is_healthy():
    client = FakeRpcClient(
        {
            "https://sol-a.example": ProviderRateLimitError("HTTP 429"),
            "https://sol-b.example": {"result": {"blockhash": "abc"}},
        }
    )
    checker = JsonRpcHealthChecker(client=client)

    health = await checker.check_solana_pool(("https://sol-a.example", "https://sol-b.example"))

    assert health.ok is True
    assert health.rate_limited is False
    assert health.detail == "2/2 endpoint ok"
    assert [call[0] for call in client.calls] == ["https://sol-a.example", "https://sol-b.example"]


@pytest.mark.asyncio
async def test_solana_pool_health_fails_only_when_all_endpoints_are_rate_limited():
    client = FakeRpcClient(
        {
            "https://sol-a.example": ProviderRateLimitError("HTTP 429"),
            "https://sol-b.example": ProviderRateLimitError("HTTP 429"),
        }
    )
    checker = JsonRpcHealthChecker(client=client)

    health = await checker.check_solana_pool(("https://sol-a.example", "https://sol-b.example"))

    assert health.ok is False
    assert health.rate_limited is True
    assert health.detail == "all endpoints rate limited"


@pytest.mark.asyncio
async def test_provider_health_service_uses_configured_alchemy_chains():
    settings = V2Settings.from_env({"ALCHEMY_API_KEY": "test-key"})
    responses = {
        "https://eth-mainnet.g.alchemy.com/v2/test-key": {"result": "0x1"},
        "https://base-mainnet.g.alchemy.com/v2/test-key": {"result": "0x2105"},
        "https://bnb-mainnet.g.alchemy.com/v2/test-key": {"result": "0x38"},
    }
    service = ProviderHealthService(settings=settings, checker=JsonRpcHealthChecker(FakeRpcClient(responses)))

    providers = await service.check()

    assert {provider.name for provider in providers} == {"eth-rpc", "base-rpc", "bsc-rpc"}
    assert all(provider.ok for provider in providers)


@pytest.mark.asyncio
async def test_provider_health_service_skips_solana_until_v2_sol_producer_is_enabled():
    settings = V2Settings.from_env(
        {
            "ALCHEMY_API_KEY": "test-key",
            "HELIUS_API_KEY": "sol-key",
        }
    )
    responses = {
        "https://eth-mainnet.g.alchemy.com/v2/test-key": {"result": "0x1"},
        "https://base-mainnet.g.alchemy.com/v2/test-key": {"result": "0x2105"},
        "https://bnb-mainnet.g.alchemy.com/v2/test-key": {"result": "0x38"},
    }
    client = FakeRpcClient(responses)
    service = ProviderHealthService(settings=settings, checker=JsonRpcHealthChecker(client))

    providers = await service.check()

    assert {provider.name for provider in providers} == {"eth-rpc", "base-rpc", "bsc-rpc"}
    assert not any("helius" in call[0] for call in client.calls)


@pytest.mark.asyncio
async def test_provider_health_service_can_enable_solana_probe():
    settings = V2Settings.from_env(
        {
            "HELIUS_API_KEY": "sol-key",
            "V2_SOLANA_PROVIDER_HEALTH_ENABLED": "true",
        }
    )
    responses = {"https://mainnet.helius-rpc.com/?api-key=sol-key": {"result": {"blockhash": "abc"}}}
    service = ProviderHealthService(settings=settings, checker=JsonRpcHealthChecker(FakeRpcClient(responses)))

    providers = await service.check()

    assert {provider.name for provider in providers} == {"sol-rpc"}
    assert providers[0].ok is True
