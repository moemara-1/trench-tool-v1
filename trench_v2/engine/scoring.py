"""Balanced alert scoring for private V2 alerts."""

from __future__ import annotations

from trench_v2.core.models import AlertDecision, AlertKind, RiskLevel, SignalScore, TokenScan


class BalancedAlertScorer:
    """Score token scans with a balanced precision/coverage policy."""

    def score(self, scan: TokenScan) -> AlertDecision:
        confidence, reasons = self._confidence(scan)
        risk = self._risk(scan)
        score = SignalScore(confidence=confidence, risk=risk, reasons=reasons)
        scan.signals = score

        kind = AlertKind.BUNDLE if scan.bundle_supply_percent >= 5 else AlertKind.OPPORTUNITY
        return AlertDecision.from_score(kind=kind, score=score, risk=scan.risk)

    def _confidence(self, scan: TokenScan) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        if scan.liquidity_usd is not None:
            if scan.liquidity_usd >= 100_000:
                score += 20
                reasons.append("strong liquidity")
            elif scan.liquidity_usd >= 25_000:
                score += 15
                reasons.append("usable liquidity")
            elif scan.liquidity_usd >= 5_000:
                score += 8
                reasons.append("thin liquidity")

        if scan.market_cap_usd is not None and 50_000 <= scan.market_cap_usd <= 5_000_000:
            score += 10
            reasons.append("tradable market-cap range")

        if scan.fresh_wallet_buys:
            points = min(30, scan.fresh_wallet_buys * 6)
            score += points
            reasons.append(f"{scan.fresh_wallet_buys} fresh buys")

        if scan.dormant_wallet_buys:
            points = min(20, scan.dormant_wallet_buys * 12)
            score += points
            reasons.append(f"{scan.dormant_wallet_buys} dormant buys")

        if scan.bundle_supply_percent >= 5:
            score += 20
            reasons.append("large coordinated supply cluster")
        elif scan.bundle_supply_percent >= 1:
            score += 15
            reasons.append("opening bundle/team-control signal")

        if scan.social_score >= 80:
            score += 15
            reasons.append("strong social signal")
        elif scan.social_score >= 50:
            score += 10
            reasons.append("credible social signal")

        return min(100, score), reasons

    def _risk(self, scan: TokenScan) -> int:
        risk_by_level = {
            RiskLevel.LOW: 15,
            RiskLevel.MEDIUM: 35,
            RiskLevel.HIGH: 70,
            RiskLevel.CRITICAL: 95,
        }
        risk = risk_by_level[scan.risk.level]

        if scan.risk.is_honeypot:
            risk = max(risk, 98)

        max_tax = max(scan.risk.buy_tax_bps or 0, scan.risk.sell_tax_bps or 0)
        if max_tax >= 2_000:
            risk = max(risk, 90)
        elif max_tax >= 1_000:
            risk = max(risk, 75)
        elif max_tax >= 500:
            risk = max(risk, 55)

        if scan.risk.liquidity_locked is False:
            risk = max(risk, 65)

        return min(100, risk)
