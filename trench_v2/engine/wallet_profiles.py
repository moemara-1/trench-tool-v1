"""Wallet profile construction from normalized transfer history."""

from __future__ import annotations

from datetime import datetime, timezone

from trench_v2.core.models import WalletProfile
from trench_v2.engine.wallet_labels import WalletBehaviorLabeler
from trench_v2.providers.evm import WalletTransfer


class WalletProfileBuilder:
    """Derive RAVN-style wallet facts from transfer history."""

    def __init__(self, labeler: WalletBehaviorLabeler | None = None):
        self.labeler = labeler or WalletBehaviorLabeler()

    def from_transfers(
        self,
        address: str,
        transfers: list[WalletTransfer],
        *,
        now: datetime | None = None,
    ) -> WalletProfile:
        current_time = now or datetime.now(timezone.utc)
        normalized_address = address.lower()
        timestamps = [transfer.timestamp for transfer in transfers if transfer.timestamp is not None]
        first_seen = min(timestamps) if timestamps else None
        last_active = max(timestamps) if timestamps else None
        previous_tokens = self._previous_tokens(transfers)
        profile = WalletProfile(
            address=address,
            age_days=(current_time - first_seen).days if first_seen else None,
            inactive_days=(current_time - last_active).days if last_active else None,
            tx_count=len(transfers),
            funding_source=self._funding_source(normalized_address, transfers),
            previous_tokens=previous_tokens,
            tokens_traded=len(previous_tokens),
            first_seen_at=first_seen,
            last_active_at=last_active,
        )
        profile.labels = sorted(label.value for label in self.labeler.positive_labels_for(profile))
        return profile

    def _funding_source(self, address: str, transfers: list[WalletTransfer]) -> str | None:
        incoming = [
            transfer
            for transfer in transfers
            if (transfer.to_address or "").lower() == address
            and transfer.category == "external"
            and transfer.from_address
        ]
        if not incoming:
            return None
        incoming.sort(key=lambda transfer: transfer.timestamp or datetime.max.replace(tzinfo=timezone.utc))
        return incoming[0].from_address

    def _previous_tokens(self, transfers: list[WalletTransfer]) -> list[str]:
        tokens: list[str] = []
        for transfer in transfers:
            token = transfer.token_address
            if not token or token in tokens:
                continue
            tokens.append(token)
        return tokens

