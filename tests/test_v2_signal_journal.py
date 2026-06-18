from datetime import datetime, timezone
import json

from trench_v2.core.models import Chain, RiskLevel
from trench_v2.engine.signal_journal import SignalJournal
from trench_v2.telegram.topics import TopicFeature


class SignalFixture:
    chain = Chain.BASE
    feature = TopicFeature.LOW_MC_FRESHIES
    topic_env_key = "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"
    token_address = "0xabc"
    symbol = "BASE"
    name = "Base Token"
    price_usd = 0.0042
    market_cap_usd = 250_000
    liquidity_usd = 75_000
    volume_24h_usd = 300_000
    buys_5m = 18
    buys_1h = 140
    buys_24h = 500
    sells_5m = 2
    sells_1h = 25
    sells_24h = 200
    pair_age_minutes = 42
    price_change_5m = 4.5
    price_change_1h = 22.0
    price_change_24h = 85.0
    url = "https://dexscreener.com/base/0xabc"
    reasons = ("deep liquidity", "strong buy pressure")
    quality_score = 98
    risk_level = RiskLevel.LOW
    buy_tax_bps = 0
    sell_tax_bps = 100
    risk_reasons = ("Honeypot.is simulation passed",)


def test_signal_journal_writes_one_json_record_per_sent_source_signal(tmp_path):
    path = tmp_path / "signals" / "v2.jsonl"
    sent_at = datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc)

    SignalJournal(path).record(SignalFixture(), sent_at=sent_at, risk_text="low | Tax B/S: 0.0%/1.0% | passed")

    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["schema_version"] == 1
    assert record["sent_at"] == sent_at.isoformat()
    assert record["chain"] == "base"
    assert record["signal_family"] == "v2_live"
    assert record["topic_env_key"] == "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"
    assert record["feature"] == "low_mc_freshies"
    assert record["token_address"] == "0xabc"
    assert record["price_usd"] == 0.0042
    assert record["quality_score"] == 98
    assert record["risk_level"] == "low"
    assert record["risk_text"] == "low | Tax B/S: 0.0%/1.0% | passed"
