from datetime import datetime, timedelta, timezone

from trench_v2.engine.backtest import (
    PricePoint,
    SignalReplayEvent,
    evaluate_signal_outcome,
    load_signal_replay_events_from_journal,
    performance_profiles_from_outcomes,
    summarize_outcomes,
)


def _time(minutes: int) -> datetime:
    return datetime(2026, 6, 18, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def test_evaluate_signal_outcome_measures_max_x_drawdown_and_time_to_peak():
    event = SignalReplayEvent(
        chain="base",
        token_address="0xtoken",
        signal_family="best_wallet_coin_week",
        score=98,
        sent_at=_time(10),
        entry_price_usd=0.001,
    )
    prices = [
        PricePoint(_time(0), 0.0005),
        PricePoint(_time(15), 0.0014),
        PricePoint(_time(25), 0.0007),
        PricePoint(_time(60), 0.0042),
    ]

    outcome = evaluate_signal_outcome(event, prices, horizon=timedelta(hours=2))

    assert outcome.max_multiple == 4.2
    assert outcome.max_drawdown_pct == 30.0
    assert outcome.minutes_to_peak == 50
    assert outcome.hit_2x is True
    assert outcome.rugged is False


def test_evaluate_signal_outcome_ignores_prices_before_signal_and_after_horizon():
    event = SignalReplayEvent(
        chain="bsc",
        token_address="0xlate",
        signal_family="v2_live",
        score=96,
        sent_at=_time(30),
        entry_price_usd=1.0,
    )
    prices = [
        PricePoint(_time(10), 10.0),
        PricePoint(_time(35), 1.2),
        PricePoint(_time(95), 5.0),
    ]

    outcome = evaluate_signal_outcome(event, prices, horizon=timedelta(minutes=30))

    assert outcome.max_multiple == 1.2
    assert outcome.minutes_to_peak == 5


def test_evaluate_signal_outcome_marks_rugged_after_severe_drawdown():
    event = SignalReplayEvent(
        chain="eth",
        token_address="0xrug",
        signal_family="v2_live",
        score=100,
        sent_at=_time(0),
        entry_price_usd=0.01,
    )
    prices = [
        PricePoint(_time(5), 0.008),
        PricePoint(_time(15), 0.0015),
    ]

    outcome = evaluate_signal_outcome(event, prices)

    assert outcome.max_multiple == 0.8
    assert outcome.max_drawdown_pct == 85.0
    assert outcome.hit_2x is False
    assert outcome.rugged is True


def test_summarize_outcomes_groups_by_signal_family_and_score_band():
    outcomes = [
        evaluate_signal_outcome(
            SignalReplayEvent("base", "0xa", "best_wallet_coin_week", 98, _time(0), 1.0),
            [PricePoint(_time(10), 3.0)],
        ),
        evaluate_signal_outcome(
            SignalReplayEvent("base", "0xb", "best_wallet_coin_week", 96, _time(0), 1.0),
            [PricePoint(_time(10), 1.4)],
        ),
        evaluate_signal_outcome(
            SignalReplayEvent("bsc", "0xc", "v2_live", 88, _time(0), 1.0),
            [PricePoint(_time(10), 0.2)],
        ),
    ]

    summary = summarize_outcomes(outcomes)

    assert summary["best_wallet_coin_week"]["count"] == 2
    assert summary["best_wallet_coin_week"]["hit_2x_rate"] == 0.5
    assert summary["best_wallet_coin_week"]["average_max_multiple"] == 2.2
    assert summary["v2_live"]["rug_rate"] == 1.0
    assert summary["score_band:95_100"]["count"] == 2
    assert summary["score_band:80_94"]["count"] == 1


def test_performance_profiles_from_outcomes_builds_best_signal_gate_inputs():
    outcomes = [
        evaluate_signal_outcome(
            SignalReplayEvent("base", "0xa", "best_wallet_coin_week", 98, _time(0), 1.0),
            [PricePoint(_time(10), 3.0)],
        ),
        evaluate_signal_outcome(
            SignalReplayEvent("base", "0xb", "best_wallet_coin_week", 96, _time(0), 1.0),
            [PricePoint(_time(10), 1.8)],
        ),
        evaluate_signal_outcome(
            SignalReplayEvent("base", "0xc", "best_wallet_coin_week", 99, _time(0), 1.0),
            [PricePoint(_time(10), 0.1)],
        ),
    ]

    profiles = performance_profiles_from_outcomes(outcomes)

    assert profiles["best_wallet_coin_week"].sample_size == 3
    assert profiles["best_wallet_coin_week"].hit_2x_rate == 1 / 3
    assert profiles["best_wallet_coin_week"].rug_rate == 1 / 3
    assert profiles["best_wallet_coin_week"].median_max_multiple == 1.8


def test_load_signal_replay_events_from_journal_uses_entry_price_records(tmp_path):
    path = tmp_path / "signals.jsonl"
    path.write_text(
        "\n".join(
            [
                (
                    '{"chain":"base","token_address":"0xbase","signal_family":"v2_live",'
                    '"quality_score":98,"sent_at":"2026-06-19T12:30:00+00:00","price_usd":0.0042}'
                ),
                (
                    '{"chain":"bsc","token_address":"0xbsc","signal_family":"best_wallet_coin_week",'
                    '"quality_score":99,"sent_at":"2026-06-19T12:35:00+00:00","price_usd":0}'
                ),
                "not json",
            ]
        ),
        encoding="utf-8",
    )

    events = load_signal_replay_events_from_journal(path)

    assert events == [
        SignalReplayEvent(
            chain="base",
            token_address="0xbase",
            signal_family="v2_live",
            score=98,
            sent_at=datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc),
            entry_price_usd=0.0042,
        )
    ]
