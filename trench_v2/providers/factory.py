"""Provider assembly for the V2 command scanner."""

from __future__ import annotations

from trench_v2.config import V2Settings
from trench_v2.core.models import Chain
from trench_v2.engine.scanner import TokenScanner
from trench_v2.providers.base import NullHolderDataProvider, NullMarketDataProvider, NullRiskProvider, RiskProvider
from trench_v2.providers.holders import MoralisHolderClusterProvider, MoralisTokenOwnersProvider
from trench_v2.providers.market import DexScreenerMarketDataProvider
from trench_v2.providers.security import (
    CompositeRiskProvider,
    GoPlusRiskProvider,
    HoneypotRiskProvider,
    RobinhoodRiskProvider,
)


def build_scanner(settings: V2Settings) -> TokenScanner:
    """Build a scanner from runtime settings.

    Explicitly constructed empty settings keep tests and local dry runs offline.
    Settings loaded from the environment enable free/public command providers by default.
    """

    if not settings.command_providers_enabled:
        return TokenScanner(
            market_data=NullMarketDataProvider(),
            risk_provider=NullRiskProvider(),
            holder_provider=NullHolderDataProvider(),
        )

    return TokenScanner(
        market_data=DexScreenerMarketDataProvider(),
        risk_provider=build_risk_provider(settings),
        holder_provider=build_holder_provider(settings),
    )


def build_risk_provider(settings: V2Settings) -> RiskProvider:
    if not settings.command_providers_enabled:
        return NullRiskProvider()

    providers: list[object] = []
    providers.append(GoPlusRiskProvider(api_key=settings.goplus_api_key))

    # Honeypot.is supports public checks in many deployments and also accepts an
    # API key when available, so keep it as the default free EVM risk source.
    providers.append(HoneypotRiskProvider(api_key=settings.honeypot_api_key))
    return CompositeRiskProvider(
        providers,
        chain_overrides={
            Chain.ROBINHOOD: RobinhoodRiskProvider(
                rpc_url=settings.rpc_url_for(Chain.ROBINHOOD),
            )
        },
    )


def build_holder_provider(settings: V2Settings):
    if not settings.command_providers_enabled or not settings.moralis_api_key:
        return NullHolderDataProvider()
    return MoralisHolderClusterProvider(
        MoralisTokenOwnersProvider(api_key=settings.moralis_api_key)
    )
