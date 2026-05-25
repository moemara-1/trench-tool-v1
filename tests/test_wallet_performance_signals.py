import pytest

from best_signals import BestSignalRouter
from wallet_performance import WalletPerformanceCandidate, best_signal_from_wallet_performance


def _wallet_candidate(
    *,
    period: str = "week",
    roi_pct: float = 420.0,
    realized_pnl_usd: float = 18_500.0,
    win_rate: float = 0.78,
    trades: int = 14,
) -> WalletPerformanceCandidate:
    return WalletPerformanceCandidate(
        chain="base",
        wallet_address="0x1111111111111111111111111111111111111111",
        period=period,
        realized_pnl_usd=realized_pnl_usd,
        roi_pct=roi_pct,
        win_rate=win_rate,
        trades=trades,
        wins=11,
        losses=3,
        top_tokens=("ALPHA", "BETA"),
        evidence_url="https://dexscreener.com/base/0x1111111111111111111111111111111111111111",
    )


def test_wallet_performance_signal_rejects_low_confidence_wallets():
    weak = _wallet_candidate(roi_pct=12.0, realized_pnl_usd=120.0, win_rate=0.45, trades=2)

    assert best_signal_from_wallet_performance(weak, min_score=95) is None


@pytest.mark.parametrize("period", ["week", "month", "year"])
def test_wallet_performance_signal_converts_top_wallet_periods(period):
    signal = best_signal_from_wallet_performance(_wallet_candidate(period=period), min_score=95)

    assert signal is not None
    assert signal.chain == "base"
    assert signal.signal_family == f"best_wallet_{period}"
    assert signal.token_address == "0x1111111111111111111111111111111111111111"
    assert signal.score >= 95
    assert any(period in reason for reason in signal.reasons)


@pytest.mark.asyncio
async def test_wallet_performance_signals_can_flow_to_unlimited_best_feed():
    router = BestSignalRouter(daily_cap=0, min_score=95)
    sent_messages: list[str] = []

    week_signal = best_signal_from_wallet_performance(_wallet_candidate(period="week"), min_score=95)
    month_signal = best_signal_from_wallet_performance(
        _wallet_candidate(
            period="month",
            roi_pct=610.0,
            realized_pnl_usd=44_000.0,
            win_rate=0.82,
            trades=21,
        ),
        min_score=95,
    )

    assert week_signal is not None
    assert month_signal is not None
    assert router.queue(week_signal) is True
    assert router.queue(month_signal) is True

    sent = await router.flush(lambda text: _record(sent_messages, text))

    assert sent == 2
    assert "Best Wallet Month" in sent_messages[0]
    assert "Best Wallet Week" in sent_messages[1]


async def _record(messages: list[str], text: str) -> bool:
    messages.append(text)
    return True
