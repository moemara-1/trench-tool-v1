import pytest

from trench_v2.core.models import Chain, HolderCluster, RiskLevel, RiskReport, TokenScan
from trench_v2.telegram.commands import CommandRouter


class FakeScanner:
    async def scan(self, address: str, chain: Chain | None = None) -> TokenScan:
        return TokenScan(
            chain=chain or Chain.SOLANA,
            address=address,
            symbol="TEST",
            name="Test Token",
            market_cap_usd=123_000,
            liquidity_usd=45_000,
            risk=RiskReport(level=RiskLevel.LOW, reasons=["fixture"]),
        )

    async def analyze(self, address: str, chain: Chain | None = None) -> TokenScan:
        return await self.scan(address, chain)

    async def find_og(self, query: str, chain: Chain | None = None) -> list[TokenScan]:
        return [await self.scan("0x1111111111111111111111111111111111111111", chain)]

    async def simulate(self, address: str, chain: Chain | None = None) -> TokenScan:
        scan = await self.scan(address, chain)
        scan.signals.reasons.append("simulation fixture")
        return scan


class FakeWatchlist:
    async def track(self, address: str, chain: Chain | None = None) -> str:
        return f"{chain.value if chain else 'auto'}:{address}"

    async def watch(self, address: str, chain: Chain | None = None) -> str:
        return await self.track(address, chain)


class SupplyScanner(FakeScanner):
    async def scan(self, address: str, chain: Chain | None = None) -> TokenScan:
        return TokenScan(
            chain=chain or Chain.ETHEREUM,
            address=address,
            symbol="LIVO",
            name="Livo",
            market_cap_usd=250_000,
            liquidity_usd=85_000,
            is_pre_bonded=True,
            pool_type="V3",
            holder_clusters=[
                HolderCluster(label="team", wallets=["0xteam"], supply_percent=42.5),
                HolderCluster(label="sniper", wallets=["0xsnipe"], supply_percent=7.0),
            ],
            risk=RiskReport(level=RiskLevel.MEDIUM, reasons=["fixture"]),
        )


class RiskScanner(FakeScanner):
    async def scan(self, address: str, chain: Chain | None = None) -> TokenScan:
        return TokenScan(
            chain=chain or Chain.BSC,
            address=address,
            symbol="RISK",
            name="Risk Token",
            risk=RiskReport(
                level=RiskLevel.HIGH,
                is_honeypot=True,
                buy_tax_bps=450,
                sell_tax_bps=2200,
                liquidity_locked=False,
                malicious_contract=True,
                reasons=["honeypot simulation failed"],
            ),
        )


@pytest.mark.asyncio
async def test_command_router_handles_scan_and_chain_hint():
    router = CommandRouter(scanner=FakeScanner(), watchlist=FakeWatchlist())

    response = await router.handle("/scan eth 0x1111111111111111111111111111111111111111")

    assert response.ok is True
    assert "ETH" in response.text
    assert "TEST" in response.text
    assert response.parse_mode == "HTML"


@pytest.mark.asyncio
async def test_command_router_tracks_without_auto_trading():
    router = CommandRouter(scanner=FakeScanner(), watchlist=FakeWatchlist())

    response = await router.handle("/track sol So11111111111111111111111111111111111111112")

    assert response.ok is True
    assert "watching" in response.text.lower()
    assert "buy" not in response.text.lower()
    assert "sell" not in response.text.lower()


@pytest.mark.asyncio
async def test_command_router_rejects_unknown_command_with_supported_surface():
    router = CommandRouter(scanner=FakeScanner(), watchlist=FakeWatchlist())

    response = await router.handle("/trade 0x1111111111111111111111111111111111111111")

    assert response.ok is False
    assert "/scan" in response.text
    assert "/simulate" in response.text


@pytest.mark.asyncio
async def test_command_router_formats_supply_distribution_and_prebond_metadata():
    router = CommandRouter(scanner=SupplyScanner(), watchlist=FakeWatchlist())

    response = await router.handle("/scan eth 0x1111111111111111111111111111111111111111")

    assert response.ok is True
    assert "Pre-bond: yes" in response.text
    assert "Pool: V3" in response.text
    assert "Team/insiders: 42.5%" in response.text
    assert "Snipers: 7.0%" in response.text


@pytest.mark.asyncio
async def test_command_router_formats_actionable_risk_metadata():
    router = CommandRouter(scanner=RiskScanner(), watchlist=FakeWatchlist())

    response = await router.handle("/analyze bnb 0x1111111111111111111111111111111111111111")

    assert response.ok is True
    assert "Honeypot: yes" in response.text
    assert "Buy tax: 4.50%" in response.text
    assert "Sell tax: 22.00%" in response.text
    assert "Liquidity locked: no" in response.text
    assert "Malicious contract: yes" in response.text
