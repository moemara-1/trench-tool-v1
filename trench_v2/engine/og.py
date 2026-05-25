"""OG token candidate filtering."""

from __future__ import annotations

from datetime import datetime, timezone

from trench_v2.core.models import Chain, TokenScan


class OgCandidateFilter:
    """Apply RAVNView-style OG filters to candidate tokens."""

    older_token_days = 180

    def filter(self, candidates: list[TokenScan]) -> list[TokenScan]:
        return [scan for scan in candidates if self.include(scan)]

    def include(self, scan: TokenScan) -> bool:
        if scan.chain is Chain.ETHEREUM and self._is_old_tax_token(scan):
            return False
        return True

    def _is_old_tax_token(self, scan: TokenScan) -> bool:
        if scan.created_at is None:
            return False
        created = scan.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days
        if age_days < self.older_token_days:
            return False
        return max(scan.risk.buy_tax_bps or 0, scan.risk.sell_tax_bps or 0) > 0
