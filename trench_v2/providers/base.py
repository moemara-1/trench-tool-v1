"""Provider protocols and safe fallback implementations."""

from __future__ import annotations

from typing import Protocol

from trench_v2.core.models import Chain, HolderCluster, RiskLevel, RiskReport, TokenScan


class MarketDataProvider(Protocol):
    async def fetch_token(self, chain: Chain, address: str) -> TokenScan:
        """Return normalized token market data."""


class RiskProvider(Protocol):
    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        """Return chain-specific token risk facts."""


class HolderDataProvider(Protocol):
    async def fetch_holder_clusters(self, chain: Chain, address: str) -> list[HolderCluster]:
        """Return holder clusters for supply distribution analysis."""


class NullMarketDataProvider:
    async def fetch_token(self, chain: Chain, address: str) -> TokenScan:
        return TokenScan(
            chain=chain,
            address=address,
            symbol="UNKNOWN",
            name="Unknown Token",
            risk=RiskReport(level=RiskLevel.MEDIUM, reasons=["no market provider configured"]),
        )


class NullRiskProvider:
    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        return RiskReport(level=RiskLevel.MEDIUM, reasons=["no risk provider configured"])


class NullHolderDataProvider:
    async def fetch_holder_clusters(self, chain: Chain, address: str) -> list[HolderCluster]:
        return []
