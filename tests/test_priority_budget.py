from datetime import datetime, timezone

from quality_budget import ELITE_BAND, HIGH_BAND, STANDARD_BAND, PriorityDailyBudget


def test_priority_budget_preserves_daily_slots_for_stronger_alerts():
    budget = PriorityDailyBudget(
        daily_cap=3,
        min_score=80,
        standard_daily_cap=1,
        high_daily_cap=1,
    )
    now = datetime(2026, 5, 24, tzinfo=timezone.utc)

    assert budget.reserve(82, now=now).allowed is True
    assert budget.reserve(84, now=now).allowed is False
    assert budget.reserve(91, now=now).allowed is True
    assert budget.reserve(92, now=now).allowed is False
    assert budget.reserve(98, now=now).allowed is True
    assert budget.reserve(99, now=now).allowed is False

    assert budget.counts_by_band(now=now) == {
        STANDARD_BAND: 1,
        HIGH_BAND: 1,
        ELITE_BAND: 1,
    }


def test_priority_budget_blocks_below_quality_floor_without_consuming_budget():
    budget = PriorityDailyBudget(daily_cap=3, min_score=80)
    now = datetime(2026, 5, 24, tzinfo=timezone.utc)

    decision = budget.reserve(79, now=now)

    assert decision.allowed is False
    assert decision.reason == "blocked by quality floor"
    assert budget.sent_count(now=now) == 0
