"""Wallet behavior labeling for holder due diligence."""

from __future__ import annotations

from trench_v2.core.models import WalletLabel, WalletProfile


class WalletBehaviorLabeler:
    """Classify wallet behavior from normalized wallet history facts."""

    fresh_max_age_days = 1
    dormant_min_inactive_days = 30
    mev_max_hold_seconds = 60
    high_volume_min_tokens = 500
    bad_dormant_rug_ratio = 0.70

    def labels_for(self, wallet: WalletProfile) -> set[WalletLabel]:
        labels: set[WalletLabel] = set()

        if wallet.age_days is not None and wallet.age_days <= self.fresh_max_age_days:
            labels.add(WalletLabel.FRESH)

        if wallet.inactive_days is not None and wallet.inactive_days >= self.dormant_min_inactive_days:
            labels.add(WalletLabel.DORMANT)

        tokens_traded = wallet.tokens_traded or wallet.tx_count or 0
        if tokens_traded >= self.high_volume_min_tokens:
            labels.add(WalletLabel.HIGH_VOLUME)

        if self._looks_like_mev(wallet):
            labels.add(WalletLabel.MEV_BOT)

        if self._looks_like_bad_dormant(wallet):
            labels.add(WalletLabel.BAD_DORMANT)
            labels.discard(WalletLabel.DORMANT)

        if wallet.previous_rugged_tokens >= 5 and wallet.previous_rugged_tokens > wallet.previous_successful_tokens:
            labels.add(WalletLabel.SERIAL_RUGGER)

        if wallet.received_transfer_from:
            labels.add(WalletLabel.TEAM_INSIDER)

        if wallet.early_buy_seconds is not None and wallet.early_buy_seconds <= 30:
            labels.add(WalletLabel.SNIPER)

        if wallet.previous_successful_tokens >= 3 and wallet.previous_successful_tokens > wallet.previous_rugged_tokens:
            labels.add(WalletLabel.SMART_MONEY)

        return labels

    def positive_labels_for(self, wallet: WalletProfile) -> set[WalletLabel]:
        labels = self.labels_for(wallet)
        if WalletLabel.BAD_DORMANT in labels or WalletLabel.SERIAL_RUGGER in labels:
            labels.discard(WalletLabel.DORMANT)
            labels.discard(WalletLabel.SMART_MONEY)
        if WalletLabel.MEV_BOT in labels:
            labels.discard(WalletLabel.SMART_MONEY)
        return labels

    def _looks_like_mev(self, wallet: WalletProfile) -> bool:
        if wallet.average_hold_seconds is None:
            return False
        pnl = wallet.pnl_usd or 0
        tokens_traded = wallet.tokens_traded or wallet.tx_count or 0
        return (
            wallet.average_hold_seconds <= self.mev_max_hold_seconds
            and pnl > 0
            and tokens_traded >= self.high_volume_min_tokens
        )

    def _looks_like_bad_dormant(self, wallet: WalletProfile) -> bool:
        total_history = wallet.previous_successful_tokens + wallet.previous_rugged_tokens
        if wallet.inactive_days is None or wallet.inactive_days < self.dormant_min_inactive_days:
            return False
        if total_history < 3:
            return False
        rug_ratio = wallet.previous_rugged_tokens / total_history
        return rug_ratio >= self.bad_dormant_rug_ratio
