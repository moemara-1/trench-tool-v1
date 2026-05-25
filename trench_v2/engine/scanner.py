"""V2 token scanner orchestration."""

from __future__ import annotations

from trench_v2.chains.adapters import default_registry
from trench_v2.core.models import Chain, TokenScan
from trench_v2.engine.og import OgCandidateFilter
from trench_v2.engine.scoring import BalancedAlertScorer
from trench_v2.providers.base import (
    HolderDataProvider,
    MarketDataProvider,
    NullHolderDataProvider,
    NullMarketDataProvider,
    NullRiskProvider,
    RiskProvider,
)


class TokenScanner:
    """Composes chain resolution, market data, risk data, and scoring."""

    def __init__(
        self,
        market_data: MarketDataProvider | None = None,
        risk_provider: RiskProvider | None = None,
        holder_provider: HolderDataProvider | None = None,
        scorer: BalancedAlertScorer | None = None,
        og_filter: OgCandidateFilter | None = None,
    ):
        self.market_data = market_data or NullMarketDataProvider()
        self.risk_provider = risk_provider or NullRiskProvider()
        self.holder_provider = holder_provider or NullHolderDataProvider()
        self.scorer = scorer or BalancedAlertScorer()
        self.og_filter = og_filter or OgCandidateFilter()

    async def scan(self, address: str, chain: Chain | None = None) -> TokenScan:
        resolved_chain = default_registry.resolve(address, chain)
        scan = await self.market_data.fetch_token(resolved_chain, address)
        scan.risk = await self.risk_provider.fetch_risk(resolved_chain, address)
        holder_clusters = await self.holder_provider.fetch_holder_clusters(resolved_chain, address)
        if holder_clusters:
            scan.holder_clusters.extend(holder_clusters)
        self.scorer.score(scan)
        return scan

    async def analyze(self, address: str, chain: Chain | None = None) -> TokenScan:
        return await self.scan(address, chain)

    async def simulate(self, address: str, chain: Chain | None = None) -> TokenScan:
        scan = await self.scan(address, chain)
        scan.signals.reasons.append("simulation placeholder: no execution path enabled")
        return scan

    async def find_og(self, query: str, chain: Chain | None = None) -> list[TokenScan]:
        resolved_chain = chain or Chain.ETHEREUM
        scan = await self.scan(query, resolved_chain)
        return self.og_filter.filter([scan])
