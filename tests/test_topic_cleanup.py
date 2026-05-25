from scripts.cleanup_v2_topics import removable_topic_keys


def test_cleanup_keeps_restored_v1_topics_with_live_producers():
    env = {
        "TELEGRAM_FRESHIES_TOPIC_ID": "1",
        "TELEGRAM_DORMANTS_TOPIC_ID": "2",
        "TELEGRAM_LATE_MIGRATION_TOPIC_ID": "3",
        "TELEGRAM_PATTERNS_TOPIC_ID": "4",
        "TELEGRAM_WIZARD_TOPIC_ID": "5",
        "TELEGRAM_BUNDLES_TOPIC_ID": "6",
        "TELEGRAM_SNS_TOPIC_ID": "7",
        "TELEGRAM_VANISH_TOPIC_ID": "8",
        "TELEGRAM_STREAMFLOW_TOPIC_ID": "9",
        "TELEGRAM_DEV_HELD_TOPIC_ID": "10",
        "TELEGRAM_GOOD_CREATOR_TOPIC_ID": "11",
        "TELEGRAM_SOCIALS_TOPIC_ID": "12",
        "TELEGRAM_STRONG_LAUNCH_TOPIC_ID": "13",
        "TELEGRAM_STRONGFLOOR_TOPIC_ID": "14",
    }

    assert removable_topic_keys(env) == set()
