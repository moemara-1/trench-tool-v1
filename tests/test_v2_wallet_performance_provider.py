import pytest
import httpx

from trench_v2.core.models import Chain
from trench_v2.providers.wallet_performance import MoralisTopTradersProvider


class FakeMoralisClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get_json(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, params))
        if isinstance(self.payload, Exception):
            raise self.payload
        if isinstance(self.payload, list):
            index = min(len(self.calls) - 1, len(self.payload) - 1)
            return self.payload[index]
        return self.payload


@pytest.mark.asyncio
async def test_moralis_top_traders_provider_normalizes_week_month_and_year_candidates():
    client = FakeMoralisClient(
        {
            "result": [
                {
                    "address": "0x1111111111111111111111111111111111111111",
                    "realized_profit_usd": "18500",
                    "realized_profit_percentage": 420,
                    "count_of_trades": 14,
                },
                {
                    "address": "0x2222222222222222222222222222222222222222",
                    "realized_profit_usd": "12500",
                    "realized_profit_percentage": 310,
                    "count_of_trades": 9,
                }
            ]
        }
    )
    provider = MoralisTopTradersProvider(api_key="key", client=client)

    candidates = await provider.best_wallets_for_token(
        chain=Chain.BASE,
        token_address="0xtoken",
        token_symbol="ALPHA",
        periods=("week", "month", "year"),
    )

    assert [candidate.period for candidate in candidates] == ["week", "week", "month", "month", "year", "year"]
    assert {call[0] for call in client.calls} == {
        "https://deep-index.moralis.io/api/v2.2/erc20/0xtoken/top-gainers"
    }
    assert [call[1]["days"] for call in client.calls] == ["7", "30", "all"]
    assert all(call[1]["chain"] == "base" for call in client.calls)
    assert candidates[0].chain == "base"
    assert candidates[0].top_tokens == ("ALPHA",)
    assert candidates[1].wallet_address == "0x2222222222222222222222222222222222222222"


@pytest.mark.asyncio
async def test_moralis_top_traders_provider_skips_unsupported_solana_chain():
    client = FakeMoralisClient({"result": []})
    provider = MoralisTopTradersProvider(api_key="key", client=client)

    assert await provider.best_wallets_for_token(
        chain=Chain.SOLANA,
        token_address="So11111111111111111111111111111111111111112",
        token_symbol="SOL",
        periods=("week",),
    ) == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_moralis_top_traders_provider_skips_unindexed_token_errors():
    request = httpx.Request("GET", "https://deep-index.moralis.io/api/v2.2/erc20/0xtoken/top-gainers")
    response = httpx.Response(404, request=request)
    client = FakeMoralisClient(httpx.HTTPStatusError("not found", request=request, response=response))
    provider = MoralisTopTradersProvider(api_key="key", client=client)

    assert await provider.best_wallets_for_token(
        chain=Chain.BSC,
        token_address="0xtoken",
        token_symbol="NOPE",
        periods=("week",),
    ) == []


@pytest.mark.asyncio
async def test_moralis_provider_converts_recent_token_buys_from_profitable_wallets():
    client = FakeMoralisClient(
        [
            {"result": []},
            {
                "result": [
                    {
                        "transactionType": "buy",
                        "walletAddress": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "totalValueUsd": 2500,
                        "bought": {"address": "0xtoken", "symbol": "ALPHA"},
                    },
                    {
                        "transactionType": "buy",
                        "walletAddress": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "totalValueUsd": 1800,
                        "bought": {"address": "0xtoken", "symbol": "ALPHA"},
                    },
                    {
                        "transactionType": "sell",
                        "walletAddress": "0xcccccccccccccccccccccccccccccccccccccccc",
                        "totalValueUsd": 9000,
                        "sold": {"address": "0xtoken", "symbol": "ALPHA"},
                    },
                ]
            },
            {
                "total_count_of_trades": 44,
                "total_realized_profit_usd": "92000",
                "total_realized_profit_percentage": 460,
                "total_buys": 28,
                "total_sells": 16,
            },
            {
                "total_count_of_trades": 31,
                "total_realized_profit_usd": "61000",
                "total_realized_profit_percentage": 380,
                "total_buys": 20,
                "total_sells": 11,
            },
        ]
    )
    provider = MoralisTopTradersProvider(api_key="key", client=client)

    candidates = await provider.best_wallets_for_token(
        chain=Chain.BASE,
        token_address="0xtoken",
        token_symbol="ALPHA",
        periods=("week",),
    )

    assert [candidate.wallet_address for candidate in candidates] == [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ]
    assert all(candidate.period == "week" for candidate in candidates)
    assert all(candidate.win_rate is None for candidate in candidates)
    assert [candidate.current_buy_usd for candidate in candidates] == [2500.0, 1800.0]
    assert client.calls[1] == (
        "https://deep-index.moralis.io/api/v2.2/erc20/0xtoken/swaps",
        {"chain": "base", "transactionTypes": "buy", "order": "DESC", "limit": "25"},
    )
    assert client.calls[2][0] == "https://deep-index.moralis.io/api/v2.2/wallets/0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/profitability/summary"
    assert client.calls[2][1] == {"chain": "base", "days": "7"}
