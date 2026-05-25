import pytest

from trench_v2.core.models import Chain
from trench_v2.providers.dexscreener import DexScreenerProvider


class FakeJsonClient:
    def __init__(self):
        self.urls = []

    async def get_json(self, url: str):
        self.urls.append(url)
        if "/latest/dex/search" in url:
            return {
                "pairs": [
                    {
                        "chainId": "bsc",
                        "url": "https://dexscreener.com/bsc/0xpair",
                        "baseToken": {"address": "0xbnb", "symbol": "BNB", "name": "BNB Token"},
                        "marketCap": 120_000,
                        "liquidity": {"usd": 40_000},
                        "volume": {"h24": 200_000},
                        "txns": {"m5": {"buys": 3}, "h1": {"buys": 30}, "h24": {"buys": 120}},
                        "pairCreatedAt": 1_800_000_000_000,
                    }
                ]
            }
        if "api.geckoterminal.com/api/v2/networks/eth/new_pools" in url:
            return {
                "data": [
                    {
                        "attributes": {
                            "name": "ETHREAL / WETH",
                            "address": "0xethpair",
                            "fdv_usd": "240000",
                            "reserve_in_usd": "60000",
                            "volume_usd": {"h24": "160000"},
                            "transactions": {
                                "m5": {"buys": 5},
                                "h1": {"buys": 45},
                                "h24": {"buys": 160},
                            },
                            "pool_created_at": "2026-05-24T18:00:00Z",
                        },
                        "relationships": {"base_token": {"data": {"id": "eth_0xeth"}}},
                    }
                ]
            }
        if "api.geckoterminal.com/api/v2/networks/" in url:
            return {"data": []}
        if url.endswith("/token-profiles/latest/v1"):
            return [
                {"chainId": "ethereum", "tokenAddress": "0xeth"},
                {"chainId": "base", "tokenAddress": "0xbase"},
            ]
        if url.endswith("/token-boosts/latest/v1"):
            return [
                {"chainId": "ethereum", "tokenAddress": "0xeth"},
                {"chainId": "bsc", "tokenAddress": "0xbnb"},
            ]
        if url.endswith("/token-boosts/top/v1"):
            return [{"chainId": "solana", "tokenAddress": "So11111111111111111111111111111111111111112"}]
        return []


@pytest.mark.asyncio
async def test_latest_profiles_includes_boosted_real_candidates_and_dedupes():
    provider = DexScreenerProvider(client=FakeJsonClient())

    profiles = await provider.latest_profiles()

    assert [(profile.chain, profile.address) for profile in profiles] == [
        (Chain.ETHEREUM, "0xeth"),
        (Chain.BASE, "0xbase"),
        (Chain.BSC, "0xbnb"),
        (Chain.SOLANA, "So11111111111111111111111111111111111111112"),
    ]


@pytest.mark.asyncio
async def test_latest_pairs_includes_search_and_geckoterminal_network_pools():
    provider = DexScreenerProvider(client=FakeJsonClient())

    pairs = await provider.latest_pairs()

    by_chain = {pair.chain: pair for pair in pairs}
    assert by_chain[Chain.BSC].token_address == "0xbnb"
    assert by_chain[Chain.ETHEREUM].token_address == "0xeth"
    assert by_chain[Chain.ETHEREUM].liquidity_usd == 60_000
    assert by_chain[Chain.ETHEREUM].buys_1h == 45
