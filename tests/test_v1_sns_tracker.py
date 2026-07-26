import pytest

import services.sns_tracker as sns_tracker
from services.sns_tracker import SNSTracker


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []
        self.get_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        self.get_urls.append(url)
        return self.responses.pop(0)

    async def post(self, url, json):
        self.urls.append(url)
        return self.responses.pop(0)


class FakeRpcManager:
    endpoint_count = 2

    def __init__(self):
        self.urls = ["https://bad.example", "https://good.example"]
        self.errors = []

    def get_rpc_url(self):
        return self.urls.pop(0)

    def report_error(self, rpc_url, is_rate_limit=False):
        self.errors.append((rpc_url, is_rate_limit))


@pytest.mark.asyncio
async def test_sns_tracker_retries_next_rpc_endpoint_after_transient_failure(monkeypatch):
    manager = FakeRpcManager()
    client = FakeClient(
        [
            FakeResponse(503),
            FakeResponse(503),
            FakeResponse(
                200,
                {
                    "result": {
                        "items": [
                            {"content": {"metadata": {"name": "wallet.sol"}}},
                        ]
                    }
                },
            ),
        ]
    )
    monkeypatch.setattr(sns_tracker, "get_rpc_manager", lambda: manager)
    monkeypatch.setattr(sns_tracker.httpx, "AsyncClient", lambda timeout: client)

    domain = await SNSTracker().get_wallet_domain("wallet")

    assert domain == "wallet.sol"
    assert client.urls == ["https://bad.example", "https://good.example"]
    assert manager.errors == [("https://bad.example", False)]


@pytest.mark.asyncio
async def test_sns_tracker_uses_public_sns_api_before_das_rpc(monkeypatch):
    manager = FakeRpcManager()
    client = FakeClient(
        [
            FakeResponse(200, {"wallet": ["alpha", "beta.sol"]}),
        ]
    )
    monkeypatch.setattr(sns_tracker, "get_rpc_manager", lambda: manager)
    monkeypatch.setattr(sns_tracker.httpx, "AsyncClient", lambda timeout: client)

    domain = await SNSTracker().get_wallet_domain("wallet")

    assert domain == "alpha.sol"
    assert client.get_urls == ["https://sns-api.bonfida.com/v2/user/domains/wallet"]
    assert client.urls == []


@pytest.mark.asyncio
async def test_sns_tracker_stats_expose_provider_errors_and_negative_lookups(monkeypatch):
    manager = FakeRpcManager()
    client = FakeClient(
        [
            FakeResponse(503),
            FakeResponse(200, {"result": {"items": []}}),
        ]
    )
    monkeypatch.setattr(sns_tracker, "get_rpc_manager", lambda: manager)
    monkeypatch.setattr(sns_tracker.httpx, "AsyncClient", lambda timeout: client)
    tracker = SNSTracker()

    domain = await tracker.get_wallet_domain("wallet")

    stats = tracker.get_stats()
    assert domain is None
    assert stats["lookups_attempted"] == 1
    assert stats["sns_api_transient_errors"] == 1
    assert stats["negative_lookups"] == 1

@pytest.mark.asyncio
async def test_sns_tracker_does_not_spend_rpc_quota_after_public_negative_lookup(monkeypatch):
    manager = FakeRpcManager()
    client = FakeClient(
        [
            FakeResponse(200, {"wallet": []}),
        ]
    )
    monkeypatch.setattr(sns_tracker, "get_rpc_manager", lambda: manager)
    monkeypatch.setattr(sns_tracker.httpx, "AsyncClient", lambda timeout: client)

    tracker = SNSTracker()
    domain = await tracker.get_wallet_domain("wallet")

    assert domain is None
    assert client.get_urls == ["https://sns-api.bonfida.com/v2/user/domains/wallet"]
    assert client.urls == []
    assert tracker.get_stats()["negative_lookups"] == 1
