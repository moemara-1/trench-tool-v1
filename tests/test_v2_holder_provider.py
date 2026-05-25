import pytest

from trench_v2.core.models import Chain, HolderCluster, RiskLevel, RiskReport, TokenScan
from trench_v2.engine.scanner import TokenScanner
from trench_v2.providers.holders import MoralisHolderClusterProvider, MoralisTokenOwnersProvider


class FakeMoralisClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get_json(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, params or {}))
        return self.response


class FakeMarketDataProvider:
    async def fetch_token(self, chain: Chain, address: str) -> TokenScan:
        return TokenScan(
            chain=chain,
            address=address,
            symbol="HOLD",
            name="Holder Token",
            risk=RiskReport(level=RiskLevel.LOW),
        )


class FakeRiskProvider:
    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        return RiskReport(level=RiskLevel.LOW)


class FakeHolderProvider:
    async def fetch_holder_clusters(self, chain: Chain, address: str) -> list[HolderCluster]:
        return [
            HolderCluster(
                label="large_holder",
                wallets=["0xholder"],
                supply_percent=12.5,
                evidence=["Moralis token owners"],
            )
        ]


@pytest.mark.asyncio
async def test_moralis_token_owners_provider_normalizes_owner_rows():
    client = FakeMoralisClient(
        {
            "result": [
                {
                    "owner_address": "0xaaa",
                    "balance_formatted": "100.5",
                    "percentage_relative_to_total_supply": 12.5,
                    "is_contract": False,
                    "owner_address_label": "Fresh Wallet",
                    "entity": None,
                    "usd_value": "2500.25",
                },
                {
                    "owner_address": "0xbbb",
                    "balance_formatted": "10",
                    "percentage_relative_to_total_supply": 1.0,
                    "is_contract": True,
                    "entity": "Uniswap",
                },
            ]
        }
    )
    provider = MoralisTokenOwnersProvider(api_key="key", client=client)

    owners = await provider.fetch_owners(Chain.BASE, "0xtoken", limit=25)

    assert owners[0].owner_address == "0xaaa"
    assert owners[0].balance_formatted == 100.5
    assert owners[0].supply_percent == 12.5
    assert owners[0].usd_value == 2500.25
    assert owners[1].is_contract is True
    assert client.calls[0][0] == "https://deep-index.moralis.io/api/v2.2/erc20/0xtoken/owners"
    assert client.calls[0][1] == {"chain": "base", "limit": "25"}


@pytest.mark.asyncio
async def test_moralis_holder_cluster_provider_builds_explainable_clusters():
    client = FakeMoralisClient(
        {
            "result": [
                {
                    "owner_address": "0xaaa",
                    "percentage_relative_to_total_supply": 12.5,
                    "is_contract": False,
                    "owner_address_label": "Fresh Wallet",
                },
                {
                    "owner_address": "0xbbb",
                    "percentage_relative_to_total_supply": 8.0,
                    "is_contract": True,
                    "entity": "Uniswap",
                },
            ]
        }
    )
    owners = MoralisTokenOwnersProvider(api_key="key", client=client)
    provider = MoralisHolderClusterProvider(owners_provider=owners)

    clusters = await provider.fetch_holder_clusters(Chain.ETHEREUM, "0xtoken")

    assert clusters == [
        HolderCluster(
            label="large_holder",
            wallets=["0xaaa"],
            supply_percent=12.5,
            evidence=["Moralis token owners", "Fresh Wallet"],
        ),
        HolderCluster(
            label="contract_holder",
            wallets=["0xbbb"],
            supply_percent=8.0,
            evidence=["Moralis token owners", "Uniswap"],
        ),
    ]


@pytest.mark.asyncio
async def test_token_scanner_attaches_holder_clusters_without_overwriting_market_data():
    scanner = TokenScanner(
        market_data=FakeMarketDataProvider(),
        risk_provider=FakeRiskProvider(),
        holder_provider=FakeHolderProvider(),
    )

    scan = await scanner.scan("0xtoken", Chain.BSC)

    assert scan.symbol == "HOLD"
    assert scan.holder_clusters[0].label == "large_holder"
    assert scan.holder_clusters[0].supply_percent == 12.5

