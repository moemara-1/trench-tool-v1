from trench_v2.core.models import (
    AlertKind,
    Chain,
    RiskLevel,
    RiskReport,
    TokenScan,
)
from trench_v2.engine.scoring import BalancedAlertScorer


def test_balanced_scorer_sends_when_multiple_independent_signals_agree():
    scan = TokenScan(
        chain=Chain.ETHEREUM,
        address="0x1111111111111111111111111111111111111111",
        symbol="EDGE",
        name="Edge Token",
        market_cap_usd=450_000,
        liquidity_usd=75_000,
        fresh_wallet_buys=5,
        dormant_wallet_buys=1,
        bundle_supply_percent=2.3,
        social_score=72,
        risk=RiskReport(level=RiskLevel.MEDIUM, reasons=["moderate holder concentration"]),
    )

    decision = BalancedAlertScorer().score(scan)

    assert decision.kind is AlertKind.OPPORTUNITY
    assert decision.should_send is True
    assert decision.priority in {"medium", "high"}
    assert decision.confidence >= 70
    assert decision.risk < 70


def test_balanced_scorer_blocks_critical_risk():
    scan = TokenScan(
        chain=Chain.BSC,
        address="0x2222222222222222222222222222222222222222",
        symbol="TRAP",
        name="Trap Token",
        market_cap_usd=200_000,
        liquidity_usd=50_000,
        fresh_wallet_buys=9,
        dormant_wallet_buys=2,
        social_score=80,
        risk=RiskReport(
            level=RiskLevel.CRITICAL,
            is_honeypot=True,
            reasons=["cannot sell in simulation"],
        ),
    )

    decision = BalancedAlertScorer().score(scan)

    assert decision.should_send is False
    assert decision.priority == "blocked"
    assert "honeypot" in decision.reason.lower()
