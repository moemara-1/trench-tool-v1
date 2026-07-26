from datetime import datetime, timezone
import json

from best_signals import BestSignalCandidate
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

def test_signal_journal_loads_only_recent_dedupe_keys(tmp_path):
    from datetime import timedelta

    path = tmp_path / "signals.jsonl"
    now = datetime.now(timezone.utc)
    rows = [
        {
            "sent_at": (now - timedelta(hours=2)).isoformat(),
            "chain": "robinhood",
            "topic_env_key": "TELEGRAM_RH_FRESHIES_TOPIC_ID",
            "token_address": "0xabc",
        },
        {
            "sent_at": (now - timedelta(hours=30)).isoformat(),
            "chain": "base",
            "topic_env_key": "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
            "token_address": "0xold",
        },
        {"sent_at": "invalid", "chain": "bsc"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    journal = SignalJournal(path)

    keys = journal.recent_dedupe_keys(now=now, max_age_hours=24)

    assert keys == {"TELEGRAM_RH_FRESHIES_TOPIC_ID:robinhood:0xabc"}


def test_signal_journal_records_confirmed_best_delivery_with_replayable_entry(tmp_path):
    path = tmp_path / "signals.jsonl"
    sent_at = datetime(2026, 7, 12, 2, 1, tzinfo=timezone.utc)
    candidate = BestSignalCandidate(
        source_label="V2 BSC Freshies",
        chain="bsc",
        signal_family="v2_live",
        token_address="0x7A848a5A8169aa6a2f603D056A749f924F504444",
        symbol="CZ",
        name="The Final Form Bull",
        score=85,
        reasons=("deep liquidity", "strong buy pressure"),
        risk_text="low | Tax B/S: 0.0%/0.0% | GoPlus found no high-risk flags",
        price_usd=0.006648,
        market_cap_usd=6_648_750,
        liquidity_usd=353_378.22,
        volume_24h_usd=1_751_390.77,
        buys_5m=33,
        buys_1h=567,
        sells_5m=11,
        sells_1h=302,
        age_minutes=12_021,
        provenance="v2_risk_checked",
        confluence_sources=("market_structure", "wallet_confluence"),
    )

    journal = SignalJournal(path)
    journal.record_best(candidate, sent_at=sent_at)

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["schema_version"] == 1
    assert record["record_type"] == "best_signal_sent"
    assert record["event_id"]
    assert record["sent_at"] == sent_at.isoformat()
    assert record["token_address"] == candidate.token_address
    assert record["price_usd"] == 0.006648
    assert record["score"] == 85
    assert record["signal_family"] == "v2_live"
    assert record["provenance"] == "v2_risk_checked"
    assert record["confluence_sources"] == ["market_structure", "wallet_confluence"]

def test_signal_journal_records_user_confirmed_outcome_feedback(tmp_path):
    path = tmp_path / "signals.jsonl"
    related_sent_at = datetime(2026, 7, 12, 2, 1, tzinfo=timezone.utc)
    recorded_at = datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)

    SignalJournal(path).record_feedback(
        chain="bsc",
        token_address="0x7A848a5A8169aa6a2f603D056A749f924F504444",
        symbol="CZ",
        verdict="positive",
        entry_price_usd=0.006648,
        observed_price_usd=0.02098,
        related_sent_at=related_sent_at,
        recorded_at=recorded_at,
        source="user_confirmed",
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["record_type"] == "best_signal_feedback"
    assert record["event_id"]
    assert record["verdict"] == "positive"
    assert record["source"] == "user_confirmed"
    assert record["related_sent_at"] == related_sent_at.isoformat()
    assert record["recorded_at"] == recorded_at.isoformat()
    assert record["observed_multiple"] == 3.1558