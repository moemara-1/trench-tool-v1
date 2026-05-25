from trench_v2.core.feature_catalog import FeatureCatalog, FeatureKind
from trench_v2.core.models import Chain
from trench_v2.telegram.topics import TopicFeature


def test_feature_catalog_covers_ravn_commands_and_supply_analysis():
    catalog = FeatureCatalog.default()

    assert catalog.get("ravnview_scan").topic_feature is TopicFeature.SCAN
    assert catalog.get("ravnview_analyze").topic_feature is TopicFeature.ANALYZE
    assert catalog.get("ravnview_track").topic_feature is TopicFeature.TRACK
    assert catalog.get("ravnview_og").topic_feature is TopicFeature.OG
    assert catalog.get("ravnview_simulate").topic_feature is TopicFeature.SIMULATE
    assert catalog.get("ravn_bundle_supply").kind is FeatureKind.SUPPLY_ANALYSIS


def test_feature_catalog_covers_bbb_eth_base_and_bnb_thresholds():
    catalog = FeatureCatalog.default()

    eth_freshies = catalog.get("eth_freshies")
    assert eth_freshies.chain is Chain.ETHEREUM
    assert eth_freshies.min_native_amount == 0.06
    assert eth_freshies.max_market_cap_usd == 500_000_000

    base_freshies = catalog.get("base_freshies")
    assert base_freshies.chain is Chain.BASE
    assert base_freshies.min_native_amount == 0.06
    assert base_freshies.max_market_cap_usd == 25_000_000

    bnb_dormants = catalog.get("bnb_dormants")
    assert bnb_dormants.chain is Chain.BSC
    assert bnb_dormants.min_native_amount == 0.3
    assert bnb_dormants.topic_feature is TopicFeature.DORMANTS


def test_feature_catalog_routes_specs_to_topic_env_keys():
    catalog = FeatureCatalog.default()

    assert catalog.topic_env_key("eth_low_mc_dormants") == "TELEGRAM_ETH_LOW_MC_DORMANTS_TOPIC_ID"
    assert catalog.topic_env_key("base_pre_approvals") == "TELEGRAM_BASE_PRE_APPROVALS_TOPIC_ID"
    assert catalog.topic_env_key("bnb_semi_dormants") == "TELEGRAM_BNB_SEMI_DORMANTS_TOPIC_ID"


def test_feature_catalog_covers_bbb_supported_chain_suites():
    catalog = FeatureCatalog.default()
    feature_ids = {feature.id for feature in catalog.all()}

    assert {
        "sol_sns_buys",
        "sol_vanish_sells",
        "sol_migrations_tracker",
        "sol_jupiter_dca",
        "sol_liquidity_inflows",
        "sol_believeapp_deploys",
    }.issubset(feature_ids)
    assert {
        "eth_bundles",
        "eth_ens_buys",
        "eth_normie_buys",
        "eth_difference_checker",
        "eth_unique_contracts",
        "eth_pre_approvals",
        "eth_launches_tracker",
    }.issubset(feature_ids)
    assert "base_curated_deploys" in feature_ids
    assert {"bnb_big_dormants", "bnb_migrations_tracker", "bnb_bundles"}.issubset(feature_ids)
