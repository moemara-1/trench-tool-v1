from datetime import datetime, timezone

from trench_v2.core.models import Chain, WalletLabel
from trench_v2.engine.wallet_profiles import WalletProfileBuilder
from trench_v2.providers.evm import WalletTransfer


def test_wallet_profile_builder_derives_age_activity_funding_and_labels():
    now = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    transfers = [
        WalletTransfer(
            chain=Chain.ETHEREUM,
            from_address="0xfunder",
            to_address="0xwallet",
            asset="ETH",
            value=1.2,
            token_address=None,
            tx_hash="0x1",
            block_number=1,
            category="external",
            timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        ),
        WalletTransfer(
            chain=Chain.ETHEREUM,
            from_address="0xwallet",
            to_address="0xpair",
            asset="RUG",
            value=100.0,
            token_address="0xrug",
            tx_hash="0x2",
            block_number=2,
            category="erc20",
            timestamp=datetime(2026, 2, 1, 12, tzinfo=timezone.utc),
        ),
        WalletTransfer(
            chain=Chain.ETHEREUM,
            from_address="0xpair",
            to_address="0xwallet",
            asset="WIN",
            value=50.0,
            token_address="0xwin",
            tx_hash="0x3",
            block_number=3,
            category="erc20",
            timestamp=datetime(2026, 4, 1, 12, tzinfo=timezone.utc),
        ),
    ]

    profile = WalletProfileBuilder().from_transfers("0xwallet", transfers, now=now)

    assert profile.address == "0xwallet"
    assert profile.age_days == 143
    assert profile.inactive_days == 53
    assert profile.tx_count == 3
    assert profile.funding_source == "0xfunder"
    assert profile.tokens_traded == 2
    assert profile.previous_tokens == ["0xrug", "0xwin"]
    assert WalletLabel.DORMANT.value in profile.labels


def test_wallet_profile_builder_marks_empty_history_without_guessing():
    profile = WalletProfileBuilder().from_transfers(
        "0xempty",
        [],
        now=datetime(2026, 5, 24, 12, tzinfo=timezone.utc),
    )

    assert profile.address == "0xempty"
    assert profile.tx_count == 0
    assert profile.age_days is None
    assert profile.labels == []

