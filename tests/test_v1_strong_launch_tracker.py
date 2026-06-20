from services.strong_launch_tracker import StrongLaunchTracker


def test_strong_launch_accepts_early_token_with_complete_socials_and_real_buy_pressure():
    tracker = StrongLaunchTracker()

    launch = tracker.evaluate_launch(
        token_address="token",
        ticker="SOC",
        token_name="Social Token",
        market_cap=125_000,
        creator_score=50,
        social_score=75,
        tokenomics_score=50,
        buy_pressure_score=55,
        age_minutes=30,
    )

    assert launch is not None
    assert launch.total_score >= tracker.MIN_SCORE_THRESHOLD


def test_strong_launch_still_blocks_old_tokens_with_good_scores():
    tracker = StrongLaunchTracker()

    launch = tracker.evaluate_launch(
        token_address="token",
        ticker="SOC",
        token_name="Social Token",
        market_cap=125_000,
        creator_score=75,
        social_score=75,
        tokenomics_score=75,
        buy_pressure_score=75,
        age_minutes=180,
    )

    assert launch is None


def test_strong_launch_stats_explain_quiet_topic_rejections():
    tracker = StrongLaunchTracker()

    tracker.evaluate_launch(
        token_address="old",
        ticker="OLD",
        token_name="Old Token",
        market_cap=125_000,
        creator_score=75,
        social_score=75,
        tokenomics_score=75,
        buy_pressure_score=75,
        age_minutes=180,
    )
    tracker.evaluate_launch(
        token_address="weak",
        ticker="WEAK",
        token_name="Weak Token",
        market_cap=20_000,
        creator_score=30,
        social_score=0,
        tokenomics_score=40,
        buy_pressure_score=20,
        age_minutes=10,
    )

    stats = tracker.get_stats()

    assert stats["candidates_evaluated"] == 2
    assert stats["rejected_by_reason"] == {
        "too_old": 1,
        "score_below_threshold": 1,
    }