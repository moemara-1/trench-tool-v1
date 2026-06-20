from datetime import datetime

from services.creator_analyzer import CreatorProfile, GoodCreatorAnalyzer


def test_good_creator_stats_explain_rejected_profiles():
    analyzer = GoodCreatorAnalyzer()
    analyzer._profiles["weak"] = CreatorProfile(
        wallet_address="weak",
        tokens_created=[],
        successful_tokens=[],
        total_wallet_value_usd=10,
        first_seen=datetime.utcnow(),
        is_good_creator=False,
        score=5,
    )
    analyzer._profiles["strong"] = CreatorProfile(
        wallet_address="strong",
        tokens_created=[],
        successful_tokens=["winner"],
        total_wallet_value_usd=10_000,
        first_seen=datetime.utcnow(),
        is_good_creator=True,
        score=80,
    )

    stats = analyzer.get_stats()

    assert stats["good_creators"] == 1
    assert stats["rejected_creators"] == 1
    assert stats["best_creator_score"] == 80