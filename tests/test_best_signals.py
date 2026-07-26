from datetime import datetime, timezone

from dataclasses import replace

import pytest

from best_signals import (
    BestSignalCandidate,
    BestSignalPerformance,
    BestSignalRouter,
    candidate_from_v1_message,
    format_best_signal,
)


class RecordingBestSender:
    def __init__(self):
        self.messages = []

    async def send(self, text: str) -> bool:
        self.messages.append(text)
        return True


def _candidate(
    score: int,
    address: str,
    symbol: str = "BEST",
    family: str = "freshies",
    chain: str = "base",
    **overrides,
) -> BestSignalCandidate:
    values = {
        "source_label": "V2 BASE Freshies",
        "chain": chain,
        "signal_family": family,
        "token_address": address,
        "symbol": symbol,
        "name": f"{symbol} Token",
        "score": score,
        "reasons": ("deep liquidity", "strong buy pressure"),
        "risk_text": "low | Tax B/S: 0.0%/0.0% | passed",
        "market_cap_usd": 250_000,
        "liquidity_usd": 120_000,
        "volume_24h_usd": 260_000,
        "buys_5m": 30,
        "buys_1h": 180,
        "sells_5m": 4,
        "sells_1h": 60,
        "age_minutes": 30,
        "backtest_text": None,
        "url": "https://dexscreener.com/base/test",
    }
    values.update(overrides)
    return BestSignalCandidate(
        **values,
    )


@pytest.mark.asyncio
async def test_best_signal_router_sends_highest_score_when_daily_cap_is_tight():
    router = BestSignalRouter(daily_cap=1, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(95, "0xstandard", "STD")) is True
    assert router.queue(_candidate(100, "0xelite", "ELITE")) is True

    sent = await router.flush(sender.send, now=datetime(2026, 5, 25, tzinfo=timezone.utc))

    assert sent == 1
    assert len(sender.messages) == 1
    assert "$ELITE" in sender.messages[0]
    assert "$STD" not in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_dedupes_by_chain_address_and_family():
    router = BestSignalRouter(daily_cap=7, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(96, "0xsame", "OLD")) is True
    assert router.queue(_candidate(99, "0xsame", "NEW")) is True

    sent = await router.flush(sender.send, now=datetime(2026, 5, 25, tzinfo=timezone.utc))

    assert sent == 1
    assert "$NEW" in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_dedupes_same_token_across_source_families():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(97, "0xsamecoin", "LIVE", family="v2_live")) is True
    assert router.queue(_candidate(100, "0xsamecoin", "WALLET", family="best_wallet_coin_week")) is True

    sent = await router.flush(sender.send, now=datetime(2026, 5, 25, tzinfo=timezone.utc))

    assert sent == 1
    assert len(sender.messages) == 1
    assert "$WALLET" in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_requires_independent_sources_before_sending_confluence():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        min_confluence_sources=2,
        confluence_window_minutes=30,
    )
    sender = RecordingBestSender()
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    market_signal = _candidate(
        98,
        "0xconfluence",
        "ALPHA",
        family="v2_live",
        confluence_source="market_structure",
    )
    repeated_market_signal = _candidate(
        100,
        "0xconfluence",
        "ALPHA",
        family="v2_live",
        confluence_source="market_structure",
    )
    wallet_signal = _candidate(
        99,
        "0xconfluence",
        "ALPHA",
        family="best_wallet_coin_week",
        confluence_source="wallet_confluence",
    )

    assert router.queue(market_signal, now=now) is True
    assert await router.flush(sender.send, now=now) == 0

    assert router.queue(repeated_market_signal, now=now) is True
    assert await router.flush(sender.send, now=now) == 0

    assert router.queue(wallet_signal, now=now) is True
    assert await router.flush(sender.send, now=now) == 1
    assert "Confluence: Market structure + Best-wallet buys" in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_allows_strong_market_component_to_confirm_elite_wallet_confluence():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=96,
        min_confluence_sources=2,
        min_confluence_component_score=90,
    )
    sender = RecordingBestSender()
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)

    market_signal = _candidate(
        91,
        "0xconfirm",
        "CONFIRM",
        family="v2_live",
        confluence_source="market_structure",
    )
    wallet_signal = _candidate(
        95,
        "0xconfirm",
        "CONFIRM",
        family="best_wallet_coin_week",
        confluence_source="wallet_confluence",
    )

    assert router.queue(market_signal, now=now) is True
    assert router.queue(wallet_signal, now=now) is True
    assert await router.flush(sender.send, now=now) == 1
    assert "Confluence: Market structure + Best-wallet buys" in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_expires_unconfirmed_candidate_before_late_corroboration():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        min_confluence_sources=2,
        confluence_window_minutes=30,
    )
    sender = RecordingBestSender()
    first_seen = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    late = datetime(2026, 7, 13, 12, 31, tzinfo=timezone.utc)

    assert router.queue(
        _candidate(
            98,
            "0xexpired",
            "STALE",
            family="v2_live",
            confluence_source="market_structure",
        ),
        now=first_seen,
    ) is True
    assert await router.flush(sender.send, now=late) == 0

    assert router.queue(
        _candidate(
            99,
            "0xexpired",
            "STALE",
            family="best_wallet_coin_week",
            confluence_source="wallet_confluence",
        ),
        now=late,
    ) is True
    assert await router.flush(sender.send, now=late) == 0
    assert router.rejected_by_reason["confluence_window_expired"] == 1


@pytest.mark.asyncio
async def test_best_signal_router_rejects_candidates_below_elite_floor():
    router = BestSignalRouter(daily_cap=7, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(94, "0xweak", "WEAK")) is False

    assert await router.flush(sender.send) == 0
    assert sender.messages == []


@pytest.mark.asyncio
async def test_best_signal_router_rejects_family_with_bad_backtest_profile():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        performance_by_family={
            "v2_live": BestSignalPerformance(
                sample_size=50,
                hit_2x_rate=0.08,
                rug_rate=0.24,
                median_max_multiple=1.05,
                average_max_multiple=1.18,
            )
        },
    )

    assert router.queue(_candidate(100, "0xbadprofile", "BAD", family="v2_live")) is False
    assert router.rejected_by_reason["backtest_hit_rate_too_low"] == 1


@pytest.mark.asyncio
async def test_best_signal_router_allows_family_with_strong_backtest_profile():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        performance_by_family={
            "v2_live": BestSignalPerformance(
                sample_size=50,
                hit_2x_rate=0.34,
                rug_rate=0.06,
                median_max_multiple=1.9,
                average_max_multiple=2.8,
            )
        },
    )
    sender = RecordingBestSender()

    assert router.queue(_candidate(98, "0xgoodprofile", "GOOD", family="v2_live")) is True
    assert await router.flush(sender.send) == 1
    assert "$GOOD" in sender.messages[0]


@pytest.mark.asyncio
async def test_best_signal_router_prints_loaded_backtest_profile_summary():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        performance_by_family={
            "v2_live": BestSignalPerformance(
                sample_size=50,
                hit_2x_rate=0.34,
                rug_rate=0.06,
                median_max_multiple=1.9,
                average_max_multiple=2.8,
            )
        },
    )
    sender = RecordingBestSender()

    assert router.queue(_candidate(98, "0xwithprofile", "PROFILE", family="v2_live")) is True
    assert await router.flush(sender.send) == 1
    assert "Replay: 34% hit 2x" in sender.messages[0]


def test_best_signal_format_includes_backtest_summary_when_available():
    message = format_best_signal(
        _candidate(
            98,
            "0xwithreplay",
            "REPLAY",
            backtest_text="Replay: 34% hit 2x, 6% rug rate, 1.9x median max",
        )
    )

    assert "Replay: 34% hit 2x" in message


@pytest.mark.asyncio
async def test_best_signal_router_rejects_100_score_with_thin_liquidity_and_dump_flow():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()

    weak_shape = _candidate(
        100,
        "0xrugshape",
        "RUG",
        chain="bsc",
        liquidity_usd=46_822,
        volume_24h_usd=484_353,
        sells_5m=120,
        sells_1h=530,
        price_change_5m=-22,
        price_change_1h=-99.9,
        price_change_24h=-99.9,
    )

    assert router.queue(weak_shape) is False
    assert await router.flush(sender.send) == 0
    assert sender.messages == []


@pytest.mark.asyncio
async def test_best_signal_router_rejects_low_score_with_unknown_risk_details():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()

    unknown_risk = _candidate(
        100,
        "0xunknownrisk",
        "UNK",
        risk_text="low | Tax B/S: ?/? | Honeypot.is unavailable",
    )

    assert router.queue(unknown_risk) is False
    assert await router.flush(sender.send) == 0
    assert sender.messages == []


@pytest.mark.asyncio
async def test_best_signal_router_allows_clean_goplus_no_high_risk_text():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    candidate = _candidate(
        98,
        "0xcleanrisk",
        "CLEAN",
        risk_text="low | Tax B/S: 0.0%/0.0% | GoPlus found no high-risk flags",
    )

    assert router.queue(candidate) is True


@pytest.mark.asyncio
async def test_best_signal_router_rejects_basic_v1_solana_freshies_without_reported_score():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()
    candidate = candidate_from_v1_message(
        """SOL Freshies
$RANDOM 5 SOL ape | MC: $100k | CA: 10m
<code>11111111111111111111111111111111</code>"""
    )

    assert candidate is not None
    assert candidate.score == 94
    assert router.queue(candidate) is False
    assert router.rejected_by_reason["score_below_min"] == 1
    assert await router.flush(sender.send) == 0
    assert sender.messages == []


@pytest.mark.asyncio
async def test_best_signal_router_exposes_gate_rejection_reason_for_unknown_evm_risk():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    unknown_risk = _candidate(
        100,
        "0xunknownrisk",
        "UNK",
        risk_text="low | Tax B/S: ?/? | Honeypot.is unavailable",
    )

    assert router.queue(unknown_risk) is False
    assert router.rejected_by_reason["risk_not_clean"] == 1


@pytest.mark.asyncio
async def test_best_signal_router_supports_unlimited_daily_cap_with_quality_floor():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(97, "0xfirst", "FIRST")) is True
    assert router.queue(_candidate(99, "0xsecond", "SECOND")) is True
    assert router.queue(_candidate(95, "0xthird", "THIRD")) is True

    sent = await router.flush(sender.send, now=datetime(2026, 5, 25, tzinfo=timezone.utc))

    assert sent == 3
    assert len(sender.messages) == 3
    assert "$SECOND" in sender.messages[0]
    assert "$FIRST" in sender.messages[1]
    assert "$THIRD" in sender.messages[2]


@pytest.mark.asyncio
async def test_best_signal_router_caps_solana_without_blocking_other_chains():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        chain_daily_caps={"solana": 1},
    )
    sender = RecordingBestSender()
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)

    assert router.queue(
        _candidate(100, "So11111111111111111111111111111111111111111", "SOL1", chain="solana", family="dormants")
    ) is True
    assert await router.flush(sender.send, now=now) == 1

    assert router.queue(
        _candidate(100, "So22222222222222222222222222222222222222222", "SOL2", chain="solana", family="dormants")
    ) is True
    assert router.queue(_candidate(98, "0xbase", "BASE", chain="base")) is True

    assert await router.flush(sender.send, now=now) == 1
    assert len(sender.messages) == 2
    assert "$BASE" in sender.messages[1]
    assert "$SOL2" not in sender.messages[1]


@pytest.mark.asyncio
async def test_best_signal_router_caps_source_family_without_blocking_other_families():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        family_daily_caps={"strongfloor": 1},
    )
    sender = RecordingBestSender()
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)

    assert router.queue(
        _candidate(100, "So11111111111111111111111111111111111111111", "FLOOR1", chain="solana", family="strongfloor")
    ) is True
    assert await router.flush(sender.send, now=now) == 1

    assert router.queue(
        _candidate(100, "So22222222222222222222222222222222222222222", "FLOOR2", chain="solana", family="strongfloor")
    ) is True
    assert router.queue(
        _candidate(100, "So33333333333333333333333333333333333333333", "DORM", chain="solana", family="dormants")
    ) is True

    assert await router.flush(sender.send, now=now) == 1
    assert len(sender.messages) == 2
    assert "$DORM" in sender.messages[1]
    assert "$FLOOR2" not in sender.messages[1]


@pytest.mark.asyncio
async def test_best_signal_router_applies_chain_cooldown():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        chain_cooldown_minutes={"solana": 60},
    )
    sender = RecordingBestSender()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)

    assert router.queue(
        _candidate(100, "So11111111111111111111111111111111111111111", "SOL1", chain="solana", family="dormants")
    ) is True
    assert await router.flush(sender.send, now=now) == 1

    assert router.queue(
        _candidate(100, "So22222222222222222222222222222222222222222", "SOL2", chain="solana", family="dormants")
    ) is True
    assert await router.flush(sender.send, now=now) == 0
    assert await router.flush(sender.send, now=datetime(2026, 5, 25, 13, 1, tzinfo=timezone.utc)) == 1


@pytest.mark.parametrize(
    ("message", "family"),
    [
        ("SOL Strong Launch\n$PUMP runner\n<code>11111111111111111111111111111111</code>", "strong_launch"),
        ("SOL Streamflow Lock\n$LOCK locked\n<code>11111111111111111111111111111111</code>", "streamflow"),
        ("SOL Dev Held\n$HOLD dev still owns supply\n<code>11111111111111111111111111111111</code>", "dev_held"),
        ("SOL Good Creator\n$MAKE previous winners\n<code>11111111111111111111111111111111</code>", "good_creator"),
        ("SOL Socials Check\n$SOCIAL smart socials\n<code>11111111111111111111111111111111</code>", "socials"),
        ("SNS Buys\n$NAME domain signal\n<code>11111111111111111111111111111111</code>", "sns"),
        ("Vanish Buys\n$VAN privacy protocol signal\n<code>11111111111111111111111111111111</code>", "vanish"),
    ],
)
def test_v1_best_signal_candidate_preserves_restored_source_family(message, family):
    candidate = candidate_from_v1_message(message)

    assert candidate is not None
    assert candidate.signal_family == family


def test_v1_best_signal_candidate_caps_score_to_reported_strength():
    message = """SOL Strongfloor
$PTAI Paladin Trump AI | Strength: 48/100
Floor: $0.000816 | Bounces: 2 | Time: 9h
MC: 977.9k
<code>2SAt9qF6YjMBz9tb1U9jAYNBBVx5jqWQ7KRXDqD2pump</code>"""

    candidate = candidate_from_v1_message(message)

    assert candidate is not None
    assert candidate.score == 48


def test_v1_best_signal_candidate_caps_unstructured_solana_heuristic_score_below_best_floor():
    message = """SOL Big Dormants
$WHALE Whale Token 5.50 SOL $120.0k
<code>9ttcxL8Ztz8nv3tQiS9Lu6KpjA2VofNrRXx7nw27z62C</code>
LS: 120d | CA: 12m
<a href="https://dexscreener.com/solana/token">XX</a>"""

    candidate = candidate_from_v1_message(message)

    assert candidate is not None
    assert candidate.score == 94


@pytest.mark.asyncio
async def test_v1_unverified_solana_message_never_reaches_best_signals():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    candidate = candidate_from_v1_message(
        """SOL Dormants
$VAULT Vault Token | Strength: 99/100
LS: 120d | CA: 9h
MC: 977.9k
<code>2SAt9qF6YjMBz9tb1U9jAYNBBVx5jqWQ7KRXDqD2pump</code>"""
    )

    assert candidate is not None
    assert candidate.score == 99
    assert router.queue(candidate) is False
    assert router.rejected_by_reason["legacy_v1_unverified"] == 1


def test_legacy_v1_candidate_stays_rejected_when_risk_text_is_later_marked_clean():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    candidate = candidate_from_v1_message(
        """SOL Strongfloor
$UNSAFE Unverified Floor | Strength: 100/100
Floor: $0.000816 | Bounces: 4 | Time: 9h
MC: 977.9k
<code>2SAt9qF6YjMBz9tb1U9jAYNBBVx5jqWQ7KRXDqD2pump</code>"""
    )

    assert candidate is not None
    forged_clean_candidate = replace(
        candidate,
        risk_text="low | Tax B/S: 0.0%/0.0% | independent risk checks passed",
    )

    assert router.queue(forged_clean_candidate) is False
    assert router.rejected_by_reason["legacy_v1_unverified"] == 1


@pytest.mark.asyncio
async def test_v1_strongfloor_without_independent_risk_evidence_never_reaches_best_signals():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    candidate = candidate_from_v1_message(
        """SOL Strongfloor
$UNSAFE Unverified Floor | Strength: 100/100
Floor: $0.000816 | Bounces: 4 | Time: 9h
MC: 977.9k
<code>2SAt9qF6YjMBz9tb1U9jAYNBBVx5jqWQ7KRXDqD2pump</code>"""
    )

    assert candidate is not None
    assert router.queue(candidate) is False
    assert router.rejected_by_reason["legacy_v1_unverified"] == 1

@pytest.mark.asyncio
async def test_best_signal_router_records_only_successfully_delivered_candidate():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sender = RecordingBestSender()
    delivered = []
    now = datetime(2026, 7, 12, 2, 1, tzinfo=timezone.utc)
    candidate = _candidate(
        98,
        "0xrecorded",
        "RECORDED",
        family="v2_live",
        price_usd=0.0042,
        provenance="v2_risk_checked",
    )

    assert router.queue(candidate) is True
    sent = await router.flush(
        sender.send,
        now=now,
        on_sent=lambda delivered_candidate, sent_at: delivered.append(
            (delivered_candidate, sent_at)
        ),
    )

    assert sent == 1
    assert delivered == [(replace(candidate, confluence_sources=("v2_live",)), now)]


@pytest.mark.asyncio
async def test_best_signal_router_does_not_record_failed_delivery():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    delivered = []
    candidate = _candidate(98, "0xfailed", "FAILED", family="v2_live")

    async def fail_send(text: str) -> bool:
        return False

    assert router.queue(candidate) is True
    assert await router.flush(
        fail_send,
        on_sent=lambda delivered_candidate, sent_at: delivered.append(
            (delivered_candidate, sent_at)
        ),
    ) == 0
    assert delivered == []


@pytest.mark.asyncio
async def test_best_signal_router_allows_deep_accumulation_reversal_without_faking_raw_score():
    router = BestSignalRouter(daily_cap=0, min_score=96)
    sender = RecordingBestSender()
    candidate = _candidate(
        85,
        "0x7A848a5A8169aa6a2f603D056A749f924F504444",
        "CZ",
        family="v2_live",
        chain="bsc",
        price_usd=0.006648,
        market_cap_usd=6_648_750,
        liquidity_usd=353_378.22,
        volume_24h_usd=1_751_390.77,
        buys_5m=33,
        sells_5m=11,
        buys_1h=567,
        sells_1h=302,
        age_minutes=12_021,
        price_change_5m=-1.32,
        price_change_1h=-7.67,
        price_change_24h=-32.23,
        provenance="v2_risk_checked",
    )

    assert router.queue(candidate) is True
    assert await router.flush(sender.send) == 1
    assert "Score: 85/100" in sender.messages[0]
    assert "Setup: Deep accumulation reversal" in sender.messages[0]


def test_best_signal_router_rejects_noisy_near_match_to_accumulation_reversal():
    router = BestSignalRouter(daily_cap=0, min_score=96)
    candidate = _candidate(
        85,
        "0xnoisy",
        "NOISY",
        family="v2_live",
        chain="bsc",
        market_cap_usd=6_648_750,
        liquidity_usd=353_378.22,
        volume_24h_usd=1_751_390.77,
        buys_5m=33,
        sells_5m=22,
        buys_1h=567,
        sells_1h=400,
        age_minutes=12_021,
        price_change_5m=-1.32,
        price_change_1h=-7.67,
        price_change_24h=-32.23,
        provenance="v2_risk_checked",
    )

    assert router.queue(candidate) is False
    assert router.rejected_by_reason["score_below_min"] == 1

@pytest.mark.asyncio
async def test_accumulation_reversal_failed_send_releases_effective_budget():
    router = BestSignalRouter(daily_cap=1, min_score=96)
    sender = RecordingBestSender()
    candidate = _candidate(
        85,
        "0xreversal-retry",
        "RETRY",
        family="v2_live",
        chain="bsc",
        market_cap_usd=6_648_750,
        liquidity_usd=353_378.22,
        volume_24h_usd=1_751_390.77,
        buys_5m=33,
        sells_5m=11,
        buys_1h=567,
        sells_1h=302,
        age_minutes=12_021,
        price_change_5m=-1.32,
        price_change_1h=-7.67,
        price_change_24h=-32.23,
        provenance="v2_risk_checked",
    )

    async def fail_send(text: str) -> bool:
        return False

    assert router.queue(candidate) is True
    assert await router.flush(fail_send) == 0
    assert await router.flush(sender.send) == 1