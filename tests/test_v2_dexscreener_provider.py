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
                        "priceUsd": "0.0042",
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
                            "base_token_price_usd": "0.0123",
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
async def test_latest_pairs_uses_dexscreener_search_by_default_without_geckoterminal():
    provider = DexScreenerProvider(client=FakeJsonClient())

    pairs = await provider.latest_pairs()

    by_chain = {pair.chain: pair for pair in pairs}
    assert by_chain[Chain.BSC].token_address == "0xbnb"
    assert by_chain[Chain.BSC].price_usd == 0.0042
    assert Chain.ETHEREUM not in by_chain
    assert not any("api.geckoterminal.com" in url for url in provider.client.urls)
    search_urls = [url for url in provider.client.urls if "/latest/dex/search" in url]
    assert any("q=base" in url for url in search_urls)
    assert any("q=aerodrome" in url for url in search_urls)
    assert any("q=baseswap" in url for url in search_urls)


@pytest.mark.asyncio
async def test_latest_pairs_can_opt_into_geckoterminal_fallback_with_dexscreener_links():
    provider = DexScreenerProvider(client=FakeJsonClient(), include_geckoterminal=True)

    pairs = await provider.latest_pairs()

    by_chain = {pair.chain: pair for pair in pairs}
    assert by_chain[Chain.ETHEREUM].token_address == "0xeth"
    assert by_chain[Chain.ETHEREUM].price_usd == 0.0123
    assert by_chain[Chain.ETHEREUM].liquidity_usd == 60_000
    assert by_chain[Chain.ETHEREUM].buys_1h == 45
    assert by_chain[Chain.ETHEREUM].url == "https://dexscreener.com/ethereum/0xeth"

@pytest.mark.asyncio
async def test_dexscreener_discovers_robinhood_profiles_and_pairs():
    class RobinhoodClient:
        def __init__(self):
            self.urls = []

        async def get_json(self, url: str):
            self.urls.append(url)
            if url.endswith("/token-profiles/latest/v1"):
                return [{"chainId": "robinhood", "tokenAddress": "0xrh"}]
            if url.endswith("/token-boosts/latest/v1") or url.endswith("/token-boosts/top/v1"):
                return []
            if "/latest/dex/search" in url and "q=robinhood" in url:
                return {
                    "pairs": [
                        {
                            "chainId": "robinhood",
                            "url": "https://dexscreener.com/robinhood/0xpair",
                            "baseToken": {"address": "0xrh", "symbol": "RH", "name": "Robinhood Token"},
                            "marketCap": 240_000,
                            "liquidity": {"usd": 80_000},
                            "volume": {"h24": 180_000},
                            "txns": {
                                "m5": {"buys": 15, "sells": 3},
                                "h1": {"buys": 90, "sells": 20},
                                "h24": {"buys": 300, "sells": 100},
                            },
                            "pairCreatedAt": 1_800_000_000_000,
                        }
                    ]
                }
            if "/latest/dex/search" in url:
                return {"pairs": []}
            return []

    client = RobinhoodClient()
    provider = DexScreenerProvider(client=client)

    profiles = await provider.latest_profiles()
    pairs = await provider.latest_pairs()

    assert [(profile.chain, profile.address) for profile in profiles] == [
        (Chain.ROBINHOOD, "0xrh")
    ]
    assert len(pairs) == 1
    assert pairs[0].chain is Chain.ROBINHOOD
    assert pairs[0].url == "https://dexscreener.com/robinhood/0xpair"
    assert any("q=robinhood" in url for url in client.urls)

@pytest.mark.asyncio
async def test_best_pair_rejects_pair_when_profile_token_is_only_the_quote_asset():
    from trench_v2.providers.dexscreener import DexTokenProfile
    requested = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"

    class QuoteOnlyClient:
        async def get_json(self, url: str):
            return {
                "pairs": [
                    {
                        "chainId": "robinhood",
                        "baseToken": {
                            "address": "0x1111111111111111111111111111111111111111",
                            "symbol": "CASHCAT",
                            "name": "Cash Cat",
                        },
                        "quoteToken": {
                            "address": requested,
                            "symbol": "WETH",
                            "name": "Wrapped Ether",
                        },
                        "liquidity": {"usd": 90000},
                    }
                ]
            }

    pair = await DexScreenerProvider(client=QuoteOnlyClient()).best_pair(
        DexTokenProfile(chain=Chain.ROBINHOOD, address=requested)
    )

    assert pair is None

@pytest.mark.asyncio
async def test_latest_profiles_continues_when_one_discovery_feed_fails():
    class PartialOutageClient:
        async def get_json(self, url: str):
            if url.endswith("/token-profiles/latest/v1"):
                raise RuntimeError("upstream timeout")
            if url.endswith("/token-boosts/latest/v1"):
                return [{"chainId": "base", "tokenAddress": "0xbase"}]
            if url.endswith("/token-boosts/top/v1"):
                return [{"chainId": "ethereum", "tokenAddress": "0xeth"}]
            return []

    profiles = await DexScreenerProvider(client=PartialOutageClient()).latest_profiles()

    assert [(profile.chain, profile.address) for profile in profiles] == [
        (Chain.BASE, "0xbase"),
        (Chain.ETHEREUM, "0xeth"),
    ]
