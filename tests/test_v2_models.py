from datetime import datetime, timezone

from trench_v2.core.models import (
    AlertDecision,
    AlertKind,
    Chain,
    HolderCluster,
    RiskLevel,
    RiskReport,
    SignalScore,
    TokenScan,
    WalletProfile,
)


def test_token_scan_exposes_shared_cross_chain_shape():
    scan = TokenScan(
        chain=Chain.SOLANA,
        address="So11111111111111111111111111111111111111112",
        symbol="SOL",
        name="Wrapped SOL",
        market_cap_usd=100_000_000,
        liquidity_usd=5_000_000,
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        creator=WalletProfile(address="creator", age_days=90, tx_count=120),
        holder_clusters=[
            HolderCluster(
                label="team",
                wallets=["creator", "insider"],
                supply_percent=12.5,
                evidence=["same funding source"],
            )
        ],
        risk=RiskReport(level=RiskLevel.LOW, reasons=["verified liquidity"]),
        signals=SignalScore(confidence=74, risk=22, reasons=["fresh inflow"]),
    )

    assert scan.chain is Chain.SOLANA
    assert scan.primary_holder_cluster.label == "team"
    assert scan.risk.level is RiskLevel.LOW
    assert scan.signals.confidence == 74


def test_alert_decision_suppresses_honeypot_even_with_high_confidence():
    decision = AlertDecision.from_score(
        kind=AlertKind.RISK,
        score=SignalScore(confidence=96, risk=98, reasons=["fresh whales"]),
        risk=RiskReport(
            level=RiskLevel.CRITICAL,
            is_honeypot=True,
            reasons=["honeypot simulation failed sell"],
        ),
    )

    assert decision.should_send is False
    assert decision.priority == "blocked"
    assert "honeypot" in decision.reason.lower()
