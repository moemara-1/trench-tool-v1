import pytest

from trench_v2.core.models import Chain
from trench_v2.providers.market import DexScreenerMarketDataProvider


class FakeDexClient:
    def __init__(self, response):
        self.response = response
        self.urls = []

    async def get_json(self, url: str):
        self.urls.append(url)
        return self.response


@pytest.mark.asyncio
async def test_dexscreener_market_provider_returns_best_pair_for_requested_chain():
    client = FakeDexClient(
        {
            "pairs": [
                {
                    "chainId": "ethereum",
                    "url": "https://dexscreener.com/ethereum/0xethpair",
                    "dexId": "uniswap",
                    "labels": ["v3"],
                    "baseToken": {
                        "address": "0x1111111111111111111111111111111111111111",
                        "symbol": "LOW",
                        "name": "Low Liquidity",
                    },
                    "marketCap": 100000,
                    "liquidity": {"usd": 1000},
                    "pairCreatedAt": 1770000000000,
                },
                {
                    "chainId": "base",
                    "url": "https://dexscreener.com/base/0xbasepair",
                    "dexId": "uniswap",
                    "labels": ["v3"],
                    "baseToken": {
                        "address": "0x1111111111111111111111111111111111111111",
                        "symbol": "WIN",
                        "name": "Winner",
                    },
                    "marketCap": 250000,
                    "liquidity": {"usd": 90000},
                    "pairCreatedAt": 1770000100000,
                },
            ]
        }
    )
    provider = DexScreenerMarketDataProvider(client=client)

    scan = await provider.fetch_token(Chain.BASE, "0x1111111111111111111111111111111111111111")

    assert scan.chain is Chain.BASE
    assert scan.symbol == "WIN"
    assert scan.name == "Winner"
    assert scan.market_cap_usd == 250000
    assert scan.liquidity_usd == 90000
    assert scan.pool_type == "V3"
    assert scan.source_urls == ["https://dexscreener.com/base/0xbasepair"]
    assert client.urls == [
        "https://api.dexscreener.com/latest/dex/tokens/0x1111111111111111111111111111111111111111"
    ]


@pytest.mark.asyncio
async def test_dexscreener_market_provider_returns_unknown_when_no_pair_matches_chain():
    client = FakeDexClient({"pairs": []})
    provider = DexScreenerMarketDataProvider(client=client)

    scan = await provider.fetch_token(Chain.ETHEREUM, "0x2222222222222222222222222222222222222222")

    assert scan.chain is Chain.ETHEREUM
    assert scan.symbol == "UNKNOWN"
    assert "no DexScreener pair found" in scan.risk.reasons

