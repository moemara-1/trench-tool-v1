from scripts.reconcile_v2_topics import TELEGRAM_TOPIC_COLORS, WANTED_TOPICS


def test_reconcile_topic_plan_creates_restored_specialty_topics():
    assert WANTED_TOPICS["TELEGRAM_BEST_SIGNALS_TOPIC_ID"].title == "Best Signals"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID"].title == "Best Wallets Week"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID"].title == "Best Wallets Month"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID"].title == "Best Wallets Year"
    assert WANTED_TOPICS["TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"].title == "Base Low MC Freshies"
    assert WANTED_TOPICS["TELEGRAM_SNS_TOPIC_ID"].title == "SNS Tracker"
    assert WANTED_TOPICS["TELEGRAM_BUNDLES_TOPIC_ID"].title == "Bundles (SOL)"
    assert WANTED_TOPICS["TELEGRAM_STRONG_LAUNCH_TOPIC_ID"].title == "Strong launches"
    assert "TELEGRAM_VANISH_TOPIC_ID" not in WANTED_TOPICS


def test_reconcile_topic_plan_assigns_allowed_icon_colors_to_every_topic():
    allowed_colors = set(TELEGRAM_TOPIC_COLORS.values())

    assert WANTED_TOPICS
    assert all(topic.icon_color in allowed_colors for topic in WANTED_TOPICS.values())
