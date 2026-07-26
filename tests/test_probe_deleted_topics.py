from scripts.probe_deleted_topics import DELETE_KEYS


def test_legacy_deleted_topic_probe_never_targets_live_routes():
    live_route_keys = {
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID",
        "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID",
        "TELEGRAM_DEV_HELD_TOPIC_ID",
        "TELEGRAM_SOL_DEV_HELD_TOPIC_ID",
        "TELEGRAM_STRONG_LAUNCH_TOPIC_ID",
        "TELEGRAM_SOL_STRONG_LAUNCH_TOPIC_ID",
        "TELEGRAM_FEEDBACK_TOPIC_ID",
    }

    assert live_route_keys.isdisjoint(DELETE_KEYS)
