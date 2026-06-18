from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from trench_v2.api import create_app
from trench_v2.config import V2Settings


@pytest.mark.asyncio
async def test_v2_health_endpoint_reports_runtime_contract():
    transport = httpx.ASGITransport(app=create_app(settings=V2Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["providers"][0]["name"] == "v2-null-provider"


@pytest.mark.asyncio
async def test_v2_health_endpoint_uses_live_signal_worker_ingestion_stats():
    app = create_app(settings=V2Settings())
    app.state.signal_worker = SimpleNamespace(
        stats=SimpleNamespace(
            last_run_at=datetime.now(timezone.utc),
            candidates_seen=123,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["processed_events"] == 123


@pytest.mark.asyncio
async def test_v2_telegram_command_endpoint_handles_scan():
    transport = httpx.ASGITransport(app=create_app(settings=V2Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v2/telegram/command",
            json={"text": "/scan sol So11111111111111111111111111111111111111112"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "SCAN SOL" in payload["text"]
    assert payload["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_v2_scan_endpoint_exposes_actionable_risk_fields():
    transport = httpx.ASGITransport(app=create_app(settings=V2Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v2/scan/eth/0x1111111111111111111111111111111111111111")

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk"]["level"] == "medium"
    assert payload["risk"]["is_honeypot"] is False
    assert payload["risk"]["buy_tax_bps"] is None
    assert payload["risk"]["sell_tax_bps"] is None
    assert payload["risk"]["liquidity_locked"] is None
    assert payload["risk"]["malicious_contract"] is False
    assert payload["holder_clusters"] == []


@pytest.mark.asyncio
async def test_v2_topics_endpoint_reports_configured_topic_inventory():
    settings = V2Settings.from_env(
        {
            "TELEGRAM_ETH_MAINNET_TOPIC_ID": "111",
            "TELEGRAM_BASE_PRE_APPROVALS_TOPIC_ID": "222",
            "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "333",
            "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
        }
    )
    transport = httpx.ASGITransport(app=create_app(settings=settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v2/topics")

    assert response.status_code == 200
    payload = response.json()
    configured = {topic["env_key"] for topic in payload["topics"] if topic["configured"]}
    assert payload["configured_count"] == 2
    assert "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID" in configured
    assert "TELEGRAM_BEST_SIGNALS_TOPIC_ID" in configured
    assert "TELEGRAM_ETH_MAINNET_TOPIC_ID" not in configured
    assert "TELEGRAM_BASE_PRE_APPROVALS_TOPIC_ID" not in configured


@pytest.mark.asyncio
async def test_v2_features_endpoint_exposes_doc_backed_catalog():
    transport = httpx.ASGITransport(app=create_app(settings=V2Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v2/features")

    assert response.status_code == 200
    payload = response.json()
    features = {feature["id"]: feature for feature in payload["features"]}
    assert features["ravnview_analyze"]["topic_feature"] == "analyze"
    assert features["eth_low_mc_dormants"]["topic_env_key"] == "TELEGRAM_ETH_LOW_MC_DORMANTS_TOPIC_ID"
    assert features["eth_low_mc_dormants"]["telegram_topic_active"] is False
    assert features["eth_freshies"]["telegram_topic_active"] is True
    assert features["eth_freshies"]["implementation_status"] == "live_producer"
    assert features["sol_patterns"]["telegram_topic_active"] is True
    assert features["sol_freshies_wizard"]["telegram_topic_active"] is True
    assert features["eth_pre_approvals"]["blocked_on"] == ["ALCHEMY_API_KEY or ETHERSCAN_API_KEY"]
    assert features["base_pre_approvals"]["min_wallets"] == 5
    assert features["bnb_dormants"]["min_native_amount"] == 0.3
