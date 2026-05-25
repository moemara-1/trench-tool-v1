from datetime import datetime, timezone

import pytest

from best_signals import BestSignalCandidate, BestSignalRouter


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
) -> BestSignalCandidate:
    return BestSignalCandidate(
        source_label="V2 BASE Freshies",
        chain="base",
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
