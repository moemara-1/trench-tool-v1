from trench_v2.config import V2Settings
from trench_v2.engine.scanner import TokenScanner
from trench_v2.providers.factory import build_risk_provider, build_scanner
from trench_v2.providers.holders import MoralisHolderClusterProvider
from trench_v2.providers.market import DexScreenerMarketDataProvider
from trench_v2.providers.security import CompositeRiskProvider


def test_provider_factory_keeps_command_providers_disabled_for_explicit_empty_settings():
    scanner = build_scanner(V2Settings())

    assert isinstance(scanner, TokenScanner)
    assert not isinstance(scanner.market_data, DexScreenerMarketDataProvider)


def test_provider_factory_enables_live_command_providers_from_env_defaults():
    scanner = build_scanner(V2Settings.from_env({}))

    assert isinstance(scanner.market_data, DexScreenerMarketDataProvider)
    assert isinstance(scanner.risk_provider, CompositeRiskProvider)


def test_provider_factory_uses_configured_security_keys():
    provider = build_risk_provider(
        V2Settings.from_env(
            {
                "GOPLUS_API_KEY": "goplus",
                "HONEYPOT_API_KEY": "honeypot",
            }
        )
    )

    assert isinstance(provider, CompositeRiskProvider)
    assert len(provider.providers) == 2


def test_provider_factory_adds_moralis_holder_provider_when_key_is_configured():
    scanner = build_scanner(V2Settings.from_env({"MORALIS_API_KEY": "moralis"}))

    assert isinstance(scanner.holder_provider, MoralisHolderClusterProvider)
