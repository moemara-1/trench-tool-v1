from datetime import datetime, timezone

import pytest

from best_signals import BestSignalCandidate, BestSignalRouter, candidate_from_v1_message


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
) -> BestSignalCandidate:
    return BestSignalCandidate(
        source_label="V2 BASE Freshies",
        chain=chain,
        signal_family=family,
        token_address=address,
        symbol=symbol,
        name=f"{symbol} Token",
        score=score,
        reasons=("deep liquidity", "strong buy pressure"),
        risk_text="low | Tax B/S: 0.0%/0.0% | passed",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        buys_5m=30,
        buys_1h=180,
        age_minutes=30,
        url="https://dexscreener.com/base/test",
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
async def test_best_signal_router_rejects_candidates_below_elite_floor():
    router = BestSignalRouter(daily_cap=7, min_score=95)
    sender = RecordingBestSender()

    assert router.queue(_candidate(94, "0xweak", "WEAK")) is False

    assert await router.flush(sender.send) == 0
    assert sender.messages == []


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

    assert router.queue(_candidate(100, "So11111111111111111111111111111111111111111", "SOL1", chain="solana")) is True
    assert await router.flush(sender.send, now=now) == 1

    assert router.queue(_candidate(100, "So22222222222222222222222222222222222222222", "SOL2", chain="solana")) is True
    assert router.queue(_candidate(98, "0xbase", "BASE", chain="base")) is True

    assert await router.flush(sender.send, now=now) == 1
    assert len(sender.messages) == 2
    assert "$BASE" in sender.messages[1]
    assert "$SOL2" not in sender.messages[1]


@pytest.mark.asyncio
async def test_best_signal_router_applies_chain_cooldown():
    router = BestSignalRouter(
        daily_cap=0,
        min_score=95,
        chain_cooldown_minutes={"solana": 60},
    )
    sender = RecordingBestSender()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)

    assert router.queue(_candidate(100, "So11111111111111111111111111111111111111111", "SOL1", chain="solana")) is True
    assert await router.flush(sender.send, now=now) == 1

    assert router.queue(_candidate(100, "So22222222222222222222222222222222222222222", "SOL2", chain="solana")) is True
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
