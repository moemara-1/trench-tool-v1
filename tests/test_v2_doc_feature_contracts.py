from datetime import datetime, timedelta, timezone

import pytest

from trench_v2.core.models import Chain, HolderCluster, RiskReport, TokenScan, WalletProfile
from trench_v2.engine.alert_policy import LowNoiseAlertPolicy
from trench_v2.engine.og import OgCandidateFilter
from trench_v2.engine.scanner import TokenScanner
from trench_v2.engine.supply import SupplyDistributionAnalyzer
from trench_v2.engine.wallet_labels import WalletBehaviorLabeler, WalletLabel


class OldTaxMarketProvider:
    async def fetch_token(self, chain: Chain, address: str) -> TokenScan:
        return TokenScan(
            chain=chain,
            address=address,
            symbol="OLDTAX",
            name="Old Tax",
            created_at=datetime.now(timezone.utc) - timedelta(days=700),
        )


class TaxRiskProvider:
    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        return RiskReport(buy_tax_bps=300, sell_tax_bps=300)


def test_wallet_labeler_flags_mev_and_filters_bad_dormants():
    labeler = WalletBehaviorLabeler()

    mev_wallet = WalletProfile(
        address="0x1111111111111111111111111111111111111111",
        pnl_usd=250_000,
        average_hold_seconds=18,
        tokens_traded=1_800,
    )
    bad_dormant = WalletProfile(
        address="0x2222222222222222222222222222222222222222",
        inactive_days=120,
        previous_successful_tokens=1,
        previous_rugged_tokens=19,
    )

    assert WalletLabel.MEV_BOT in labeler.labels_for(mev_wallet)
    assert WalletLabel.HIGH_VOLUME in labeler.labels_for(mev_wallet)
    assert WalletLabel.BAD_DORMANT in labeler.labels_for(bad_dormant)
    assert WalletLabel.DORMANT not in labeler.positive_labels_for(bad_dormant)


def test_supply_distribution_groups_team_insiders_snipers_and_terminal_users():
    scan = TokenScan(
        chain=Chain.SOLANA,
        address="21rKrtBzibPAZHAHQRzGiGDSh7XimCKB2a8VgsjZpump",
        symbol="CHUD",
        name="Chud",
        holder_clusters=[
            HolderCluster(
                label="team",
                wallets=["creator", "insider-a"],
                supply_percent=38.0,
                evidence=["same funding source"],
            ),
            HolderCluster(
                label="insider",
                wallets=["insider-b"],
                supply_percent=12.3,
                evidence=["transfer fan-out"],
            ),
            HolderCluster(label="sniper", wallets=["snipe-a"], supply_percent=8.0),
            HolderCluster(label="terminal", wallets=["bot-a"], supply_percent=2.5),
        ],
    )

    report = SupplyDistributionAnalyzer().summarize(scan)

    assert report.team_insider_supply_percent == 50.3
    assert report.sniper_supply_percent == 8.0
    assert report.terminal_user_supply_percent == 2.5
    assert report.high_team_control is True
    assert "creator" in report.drilldown_wallets


def test_og_filter_suppresses_old_eth_tax_tokens_but_keeps_prebond_pool_metadata():
    old_tax = TokenScan(
        chain=Chain.ETHEREUM,
        address="0x3333333333333333333333333333333333333333",
        symbol="OLDTAX",
        name="Old Tax",
        created_at=datetime.now(timezone.utc) - timedelta(days=700),
        risk=RiskReport(buy_tax_bps=300, sell_tax_bps=300),
    )
    prebond = TokenScan(
        chain=Chain.ETHEREUM,
        address="0x4444444444444444444444444444444444444444",
        symbol="LIVO",
        name="Livo",
        is_pre_bonded=True,
        pool_type="V3",
        risk=RiskReport(buy_tax_bps=0, sell_tax_bps=0),
    )

    filtered = OgCandidateFilter().filter([old_tax, prebond])

    assert [scan.symbol for scan in filtered] == ["LIVO"]
    assert filtered[0].pool_type == "V3"
    assert filtered[0].is_pre_bonded is True


def test_low_noise_alert_policy_dedupes_cools_down_and_caps_daily_volume():
    policy = LowNoiseAlertPolicy(daily_cap=2, cooldown_seconds=60)
    now = datetime(2026, 5, 10, 12, tzinfo=timezone.utc)
    scan_a = TokenScan(chain=Chain.BASE, address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", symbol="A", name="A")
    scan_b = TokenScan(chain=Chain.BASE, address="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", symbol="B", name="B")
    scan_c = TokenScan(chain=Chain.BASE, address="0xcccccccccccccccccccccccccccccccccccccccc", symbol="C", name="C")

    assert policy.should_send(scan_a, topic="opportunity", now=now).allowed is True
    policy.record_sent(scan_a, topic="opportunity", now=now)

    duplicate = policy.should_send(scan_a, topic="opportunity", now=now + timedelta(seconds=10))
    assert duplicate.allowed is False
    assert "cooldown" in duplicate.reason

    assert policy.should_send(scan_b, topic="opportunity", now=now + timedelta(seconds=61)).allowed is True
    policy.record_sent(scan_b, topic="opportunity", now=now + timedelta(seconds=61))

    capped = policy.should_send(scan_c, topic="opportunity", now=now + timedelta(seconds=62))
    assert capped.allowed is False
    assert "daily cap" in capped.reason


@pytest.mark.asyncio
async def test_token_scanner_applies_og_filter_to_old_tax_tokens():
    scanner = TokenScanner(market_data=OldTaxMarketProvider(), risk_provider=TaxRiskProvider())

    candidates = await scanner.find_og("0x3333333333333333333333333333333333333333", Chain.ETHEREUM)

    assert candidates == []
