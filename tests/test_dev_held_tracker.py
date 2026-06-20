from datetime import datetime, timedelta

from services.dev_held_tracker import DevHeldTracker


def test_dev_held_tracker_uses_observed_initial_balance_for_hold_checks():
    tracker = DevHeldTracker()
    tracker.record_dev_wallet("TokenMint111111111111111111111111111111111111", "wallet", 125_000)
    holding = tracker.get_holdings_to_check()["TokenMint111111111111111111111111111111111111"]
    holding.first_seen = datetime.utcnow() - timedelta(hours=2)

    result = tracker.update_holding("TokenMint111111111111111111111111111111111111", 121_000)

    assert result is holding
    assert tracker.check_should_alert("TokenMint111111111111111111111111111111111111") is True
    assert holding.has_sold is False
    assert holding.holding_hours >= 1


def test_dev_held_tracker_ignores_missing_initial_balance():
    tracker = DevHeldTracker()

    tracker.record_dev_wallet("TokenMint111111111111111111111111111111111111", "wallet", 0)

    assert tracker.get_holdings_to_check() == {}
    assert tracker.get_stats()["tokens_tracked"] == 0


def test_dev_held_stats_explain_pending_and_sold_states():
    tracker = DevHeldTracker()
    tracker.record_dev_wallet("PendingToken111111111111111111111111111111111", "wallet", 100)
    tracker.update_holding("PendingToken111111111111111111111111111111111", 100)
    tracker.record_dev_wallet("SoldToken111111111111111111111111111111111111", "wallet", 100)
    tracker.update_holding("SoldToken111111111111111111111111111111111111", 80)

    stats = tracker.get_stats()

    assert stats["pending_hold_threshold"] == 1
    assert stats["sold_or_reduced_supply"] == 1
    assert stats["rejected_by_reason"]["sold_supply"] == 1