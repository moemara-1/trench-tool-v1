from trench_v2.config import V2Settings
from trench_v2.core.models import Chain
from trench_v2.telegram.topics import (
    TopicFeature,
    build_default_topic_plan,
    topic_env_key,
    working_topic_ids,
)


def test_topic_env_keys_are_chain_specific():
    assert topic_env_key(Chain.ETHEREUM, TopicFeature.FRESHIES) == "TELEGRAM_ETH_FRESHIES_TOPIC_ID"
    assert topic_env_key(Chain.BASE, TopicFeature.DEPLOYS) == "TELEGRAM_BASE_DEPLOYS_TOPIC_ID"
    assert topic_env_key(Chain.BSC, TopicFeature.DORMANTS) == "TELEGRAM_BNB_DORMANTS_TOPIC_ID"


def test_default_topic_plan_covers_live_signal_suites():
    plan = build_default_topic_plan()
    pairs = {(target.chain, target.feature) for target in plan}

    assert (Chain.BASE, TopicFeature.DEPLOYS) in pairs
    assert (Chain.SOLANA, TopicFeature.FRESHIES) in pairs
    assert (Chain.SOLANA, TopicFeature.DORMANTS) in pairs
    assert (Chain.SOLANA, TopicFeature.MIGRATIONS_TRACKER) in pairs
    assert (Chain.SOLANA, TopicFeature.PATTERNS) in pairs
    assert (Chain.SOLANA, TopicFeature.WIZARD) in pairs
    assert (Chain.ETHEREUM, TopicFeature.LOW_MC_FRESHIES) in pairs
    assert (Chain.BSC, TopicFeature.BIG_FRESHIES) in pairs
    assert (Chain.SOLANA, TopicFeature.BUNDLES) not in pairs
    assert (Chain.SOLANA, TopicFeature.GOOD_CREATOR) not in pairs
    assert (Chain.SOLANA, TopicFeature.SNS) not in pairs
    assert (Chain.SOLANA, TopicFeature.STREAMFLOW) not in pairs
    assert (Chain.SOLANA, TopicFeature.STRONG_LAUNCH) not in pairs
    assert (Chain.SOLANA, TopicFeature.SEMI_DORMANTS_SELLS) not in pairs
    assert (Chain.SOLANA, TopicFeature.LIQUIDITY_INFLOWS) not in pairs
    assert (Chain.SOLANA, TopicFeature.BELIEVEAPP_DEPLOYS) not in pairs
    assert (Chain.ETHEREUM, TopicFeature.SCAN) not in pairs
    assert (Chain.BASE, TopicFeature.SCAN) not in pairs
    assert (Chain.BSC, TopicFeature.SCAN) not in pairs

    global_pairs = {(target.chain, target.feature) for target in plan}
    assert (None, TopicFeature.BEST_WALLETS_WEEK) in global_pairs
    assert (None, TopicFeature.BEST_WALLETS_MONTH) in global_pairs
    assert (None, TopicFeature.BEST_WALLETS_YEAR) in global_pairs


def test_working_topic_ids_filters_zero_and_missing_values():
    settings = V2Settings.from_env(
        {
            "TELEGRAM_ETH_FRESHIES_TOPIC_ID": "123",
            "TELEGRAM_ETH_DORMANTS_TOPIC_ID": "0",
            "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "",
            "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "456",
        }
    )

    topics = working_topic_ids(settings)

    assert topics["TELEGRAM_ETH_FRESHIES_TOPIC_ID"] == 123
    assert topics["TELEGRAM_BNB_FRESHIES_TOPIC_ID"] == 456
    assert "TELEGRAM_ETH_DORMANTS_TOPIC_ID" not in topics
    assert "TELEGRAM_BASE_DEPLOYS_TOPIC_ID" not in topics
