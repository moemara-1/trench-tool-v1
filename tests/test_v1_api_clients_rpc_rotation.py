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

