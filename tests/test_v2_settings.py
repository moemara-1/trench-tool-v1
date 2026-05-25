from trench_v2.config import V2Settings
from trench_v2.core.models import Chain


def test_settings_builds_alchemy_urls_for_eth_base_and_bsc():
    settings = V2Settings.from_env({"ALCHEMY_API_KEY": "test-key"})

    assert settings.rpc_url_for(Chain.ETHEREUM) == "https://eth-mainnet.g.alchemy.com/v2/test-key"
    assert settings.rpc_url_for(Chain.BASE) == "https://base-mainnet.g.alchemy.com/v2/test-key"
    assert settings.rpc_url_for(Chain.BSC) == "https://bnb-mainnet.g.alchemy.com/v2/test-key"
    assert settings.command_providers_enabled is True


def test_settings_reads_optional_provider_keys():
    settings = V2Settings.from_env(
        {
            "GOPLUS_API_KEY": "goplus",
            "HONEYPOT_API_KEY": "honeypot",
            "ETHERSCAN_API_KEY": "etherscan",
            "MORALIS_API_KEY": "moralis",
            "BITQUERY_API_KEY": "bitquery",
        }
    )

    assert settings.goplus_api_key == "goplus"
    assert settings.honeypot_api_key == "honeypot"
    assert settings.etherscan_api_key == "etherscan"
    assert settings.moralis_api_key == "moralis"
    assert settings.bitquery_api_key == "bitquery"


def test_signal_cycle_default_can_cover_all_live_topics():
    settings = V2Settings.from_env({})

    assert settings.signal_max_alerts_per_cycle == 14


def test_signal_quality_default_prioritizes_actionable_alerts():
    settings = V2Settings.from_env({})

    assert settings.signal_min_quality == 82
    assert settings.signal_daily_cap == 30
    assert settings.best_signals_daily_cap == 7
    assert settings.best_signals_min_score == 95


def test_settings_prefers_explicit_v1_bsc_rpc_url_over_alchemy_bsc_url():
    settings = V2Settings.from_env(
        {
            "ALCHEMY_API_KEY": "test-key",
            "BSC_BSC_RPC_URL": "https://existing-bsc.example/rpc",
        }
    )

    assert settings.rpc_url_for(Chain.BSC) == "https://existing-bsc.example/rpc"


def test_settings_supports_reusable_v1_secret_names():
    settings = V2Settings.from_env(
        {
            "HELIUS_API_KEYS": "helius-a,helius-b",
            "SOLANA_RPC_URL": "https://solana.example/rpc",
            "TELEGRAM_CHAT_ID": "-100123",
            "REDIS_URL": "redis://example",
        }
    )

    assert settings.helius_api_keys == ("helius-a", "helius-b")
    assert settings.rpc_url_for(Chain.SOLANA) == "https://solana.example/rpc"
    assert settings.telegram_chat_id == "-100123"
    assert settings.redis_url == "redis://example"


def test_settings_builds_solana_rpc_pool_from_helius_keys():
    settings = V2Settings.from_env(
        {
            "HELIUS_API_KEYS": "helius-a,helius-b",
            "SOLANA_RPC_URL": "https://solana.example/rpc",
        }
    )

    assert settings.rpc_urls_for(Chain.SOLANA) == (
        "https://solana.example/rpc",
        "https://mainnet.helius-rpc.com/?api-key=helius-a",
        "https://mainnet.helius-rpc.com/?api-key=helius-b",
    )
