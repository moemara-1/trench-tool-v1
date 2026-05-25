from trench_v2.config import V2Settings
from trench_v2.core.feature_status import FeatureReadinessService


def test_feature_readiness_marks_live_topics_as_active():
    service = FeatureReadinessService(
        settings=V2Settings.from_env({"TELEGRAM_ETH_FRESHIES_TOPIC_ID": "123"})
    )

    readiness = service.for_feature("eth_freshies")

    assert readiness.status == "live_producer"
    assert readiness.blocked_on == []


def test_feature_readiness_marks_evm_log_features_ready_with_etherscan_key():
    service = FeatureReadinessService(
        settings=V2Settings.from_env({"ETHERSCAN_API_KEY": "key"})
    )

    readiness = service.for_feature("eth_pre_approvals")

    assert readiness.status == "provider_ready"
    assert readiness.blocked_on == []


def test_feature_readiness_marks_holder_features_as_key_gated():
    service = FeatureReadinessService(settings=V2Settings())

    readiness = service.for_feature("bnb_bundles")

    assert readiness.status == "needs_api_key"
    assert readiness.blocked_on == ["MORALIS_API_KEY or ETHERSCAN_API_KEY"]


def test_feature_readiness_marks_unconfirmed_solana_protocols_as_blocked():
    service = FeatureReadinessService(
        settings=V2Settings.from_env({"HELIUS_API_KEY": "helius"})
    )

    readiness = service.for_feature("sol_boop_deploys")

    assert readiness.status == "blocked_external_source"
    assert readiness.blocked_on == ["official protocol program/API source"]

