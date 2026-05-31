import pytest

from best_signals import BestSignalRouter
from wallet_performance import (
    WalletPerformanceCandidate,
    best_signal_from_wallet_performance,
    best_signal_from_wallet_token_confluence,
)


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


def test_wallet_token_confluence_requires_multiple_profitable_wallets():
    signal = best_signal_from_wallet_token_confluence(
        chain="base",
        token_address="0xtoken",
        token_symbol="ALPHA",
        token_name="Alpha Token",
        period="week",
        wallet_candidates=(_wallet_candidate(),),
        min_score=95,
    )

    assert signal is None


def test_wallet_token_confluence_alerts_coin_without_wallet_addresses():
    wallet_a = _wallet_candidate(
        roi_pct=900,
        realized_pnl_usd=80_000,
        win_rate=0.9,
        trades=24,
    )
    wallet_b = _wallet_candidate(
        roi_pct=720,
        realized_pnl_usd=55_000,
        win_rate=0.82,
        trades=18,
    )

    signal = best_signal_from_wallet_token_confluence(
        chain="base",
        token_address="0xtoken",
        token_symbol="ALPHA",
        token_name="Alpha Token",
        period="week",
        wallet_candidates=(wallet_a, wallet_b),
        min_score=95,
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        buys_5m=30,
        buys_1h=180,
        age_minutes=30,
        url="https://dexscreener.com/base/0xtoken",
    )

    assert signal is not None
    assert signal.source_label == "Best Wallet Coin Week"
    assert signal.signal_family == "best_wallet_coin_week"
    assert signal.token_address == "0xtoken"
    assert signal.symbol == "ALPHA"
    assert signal.score >= 95
    rendered = " ".join((signal.source_label, signal.name, *signal.reasons))
    assert "0x1111111111111111111111111111111111111111" not in rendered
    assert any("2 profitable wallets" in reason for reason in signal.reasons)


def test_wallet_token_confluence_allows_new_token_two_trade_top_trader_rows_but_caps_low_pnl_score():
    wallets = tuple(
        WalletPerformanceCandidate(
            chain="eth",
            wallet_address=f"0x{i:040d}",
            period="year",
            realized_pnl_usd=200.0,
            roi_pct=1500.0,
            win_rate=1.0,
            trades=2,
            wins=2,
            losses=0,
            top_tokens=("COIN",),
        )
        for i in range(1, 6)
    )

    signal = best_signal_from_wallet_token_confluence(
        chain="eth",
        token_address="0xcoin",
        token_symbol="COIN",
        token_name="Coin",
        period="year",
        wallet_candidates=wallets,
        min_score=92,
    )

    assert signal is not None
    assert signal.score == 92
    assert best_signal_from_wallet_token_confluence(
        chain="eth",
        token_address="0xcoin",
        token_symbol="COIN",
        token_name="Coin",
        period="year",
        wallet_candidates=wallets,
        min_score=95,
    ) is None


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
