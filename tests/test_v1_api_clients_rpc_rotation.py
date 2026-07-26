from datetime import datetime, timedelta

import pytest

from services import api_clients


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeRPCManager:
    endpoint_count = 2

    def __init__(self):
        self.urls = ["https://limited.example/rpc", "https://healthy.example/rpc"]
        self.calls = []
        self.errors = []

    def get_rpc_url(self):
        url = self.urls[len(self.calls)]
        self.calls.append(url)
        return url

    def report_error(self, rpc_url, is_rate_limit=False):
        self.errors.append((rpc_url, is_rate_limit))


class _FakeAsyncClient:
    posts = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, timeout=None):
        self.posts.append((url, json["method"]))
        if url == "https://limited.example/rpc":
            return _FakeResponse(429, {"error": {"message": "rate limited"}})

        block_time = int((datetime.utcnow() - timedelta(hours=6)).timestamp())
        return _FakeResponse(
            200,
            {
                "result": [
                    {"signature": "sig-new", "blockTime": block_time + 60},
                    {"signature": "sig-old", "blockTime": block_time},
                ]
            },
        )


@pytest.mark.asyncio
async def test_helius_wallet_age_rotates_and_reports_rate_limited_rpc(monkeypatch):
    manager = _FakeRPCManager()
    _FakeAsyncClient.posts = []
    monkeypatch.setattr(api_clients, "get_rpc_manager", lambda: manager, raising=False)
    monkeypatch.setattr(api_clients.httpx, "AsyncClient", _FakeAsyncClient)

    age_days, tx_count = await api_clients.HeliusClient().get_wallet_age_and_tx_count("wallet")

    assert tx_count == 2
    assert age_days == 0
    assert manager.errors == [("https://limited.example/rpc", True)]
    assert _FakeAsyncClient.posts == [
        ("https://limited.example/rpc", "getSignaturesForAddress"),
        ("https://healthy.example/rpc", "getSignaturesForAddress"),
    ]

@pytest.mark.asyncio
async def test_token_metadata_fallback_rotates_and_reports_rate_limited_rpc(monkeypatch):
    manager = _FakeRPCManager()
    _FakeAsyncClient.posts = []
    monkeypatch.setattr(api_clients, "get_rpc_manager", lambda: manager, raising=False)
    monkeypatch.setattr(api_clients.httpx, "AsyncClient", _FakeAsyncClient)

    class MetadataClient(_FakeAsyncClient):
        async def post(self, url, json, timeout=None):
            self.posts.append((url, json["method"]))
            if url == "https://limited.example/rpc":
                return _FakeResponse(429, {"error": {"message": "rate limited"}})
            return _FakeResponse(
                200,
                {
                    "result": {
                        "content": {"metadata": {"symbol": "META", "name": "Metadata Token"}}
                    }
                },
            )

    fetcher = api_clients.TokenDataFetcher()
    token_data = await fetcher._try_helius_metadata(MetadataClient(), "TokenMint")

    assert token_data is not None
    assert token_data.symbol == "META"
    assert manager.errors == [("https://limited.example/rpc", True)]
    assert _FakeAsyncClient.posts == [
        ("https://limited.example/rpc", "getAsset"),
        ("https://healthy.example/rpc", "getAsset"),
    ]



@pytest.mark.asyncio
async def test_token_data_fetcher_enriches_dex_pair_with_actual_pump_creator(monkeypatch):
    fetcher = api_clients.TokenDataFetcher()
    dex_data = api_clients.EnhancedTokenData(
        address="CreatorMintpump",
        symbol="CREATOR",
        name="Creator Token",
        price_usd=0.01,
        market_cap=100_000,
        liquidity_usd=25_000,
        volume_24h=200_000,
        age_minutes=10,
        holder_count=None,
        dex_name="pumpfun",
        is_pump_fun=True,
    )
    pump_data = api_clients.EnhancedTokenData(
        address="CreatorMintpump",
        symbol="CREATOR",
        name="Creator Token",
        price_usd=None,
        market_cap=100_000,
        liquidity_usd=None,
        volume_24h=None,
        age_minutes=10,
        holder_count=None,
        dex_name="pump.fun",
        is_pump_fun=True,
    )
    pump_data.creator_address = "ActualCreator111111111111111111111111111111"

    async def from_dex(_client, _address):
        return dex_data

    async def from_pump(_client, _address):
        return pump_data

    monkeypatch.setattr(fetcher, "_try_dexscreener", from_dex)
    monkeypatch.setattr(fetcher, "_try_pumpfun_api", from_pump)

    token = await fetcher.get_token_data("CreatorMintpump")

    assert token is dex_data
    assert getattr(token, "creator_address", None) == "ActualCreator111111111111111111111111111111"

@pytest.mark.asyncio
async def test_pumpfun_v3_metadata_uses_current_endpoint_and_data_envelope():
    class PumpV3Client:
        def __init__(self):
            self.urls = []

        async def get(self, url, timeout=None):
            self.urls.append((url, timeout))
            return _FakeResponse(
                200,
                {
                    "data": {
                        "symbol": "V3",
                        "name": "V3 Token",
                        "creator": "Creator1111111111111111111111111111111111111",
                        "usd_market_cap": 125_000,
                        "created_timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                },
            )

    client = PumpV3Client()
    token = await api_clients.TokenDataFetcher()._try_pumpfun_api(client, "MintV3pump")

    assert token is not None
    assert token.symbol == "V3"
    assert token.creator_address == "Creator1111111111111111111111111111111111111"
    assert token.market_cap == 125_000
    assert client.urls == [("https://frontend-api-v3.pump.fun/coins/MintV3pump", 5.0)]

@pytest.mark.asyncio
async def test_jupiter_client_uses_dexscreener_price_without_legacy_jupiter_hostname(monkeypatch):
    class PriceClient:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout))
            return _FakeResponse(
                200,
                {
                    "pairs": [
                        {
                            "chainId": "solana",
                            "baseToken": {"address": "So11111111111111111111111111111111111111112"},
                            "priceUsd": "148.25",
                            "liquidity": {"usd": 900_000},
                        }
                    ]
                },
            )

    monkeypatch.setattr(api_clients.httpx, "AsyncClient", PriceClient)

    price = await api_clients.JupiterClient().get_sol_price()

    assert price == 148.25
    assert PriceClient.calls == [
        (
            "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112",
            None,
            5.0,
        )
    ]
