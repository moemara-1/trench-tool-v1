from scripts.cleanup_v2_topics import removable_topic_keys


def test_cleanup_keeps_restored_topics_for_diagnostics_and_producer_repair():
    env = {
        "TELEGRAM_FRESHIES_TOPIC_ID": "1",
        "TELEGRAM_SOL_FRESHIES_TOPIC_ID": "15",
        "TELEGRAM_DORMANTS_TOPIC_ID": "2",
        "TELEGRAM_SOL_DORMANTS_TOPIC_ID": "16",
        "TELEGRAM_LATE_MIGRATION_TOPIC_ID": "3",
        "TELEGRAM_SOL_MIGRATIONS_TRACKER_TOPIC_ID": "17",
        "TELEGRAM_PATTERNS_TOPIC_ID": "4",
        "TELEGRAM_SOL_PATTERNS_TOPIC_ID": "18",
        "TELEGRAM_WIZARD_TOPIC_ID": "5",
        "TELEGRAM_SOL_WIZARD_TOPIC_ID": "19",
        "TELEGRAM_BUNDLES_TOPIC_ID": "6",
        "TELEGRAM_SNS_TOPIC_ID": "7",
        "TELEGRAM_STREAMFLOW_TOPIC_ID": "9",
        "TELEGRAM_DEV_HELD_TOPIC_ID": "10",
        "TELEGRAM_GOOD_CREATOR_TOPIC_ID": "11",
        "TELEGRAM_SOCIALS_TOPIC_ID": "12",
        "TELEGRAM_STRONG_LAUNCH_TOPIC_ID": "13",
        "TELEGRAM_STRONGFLOOR_TOPIC_ID": "14",
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "20",
        "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID": "21",
        "TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID": "22",
        "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID": "23",
        "TELEGRAM_FEEDBACK_TOPIC_ID": "24",
    }

    assert removable_topic_keys(env) == set()


def test_cleanup_removes_vanish_topic_after_source_was_disabled():
    assert removable_topic_keys({"TELEGRAM_VANISH_TOPIC_ID": "8"}) == {"TELEGRAM_VANISH_TOPIC_ID"}
