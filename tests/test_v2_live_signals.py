from datetime import datetime, timedelta, timezone
import json

import pytest

from best_signals import BestSignalRouter
from trench_v2.config import V2Settings
from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.engine.live_signals import LiveSignalWorker
from trench_v2.providers.dexscreener import DexPair, DexTokenProfile
from trench_v2.telegram.topics import TopicFeature
from wallet_performance import WalletPerformanceCandidate


class FakeDiscoveryProvider:
    def __init__(self, pair: DexPair | None):
        self.pair = pair
        self.best_pair_calls = 0

    async def latest_profiles(self):
        return [DexTokenProfile(chain=Chain.BASE, address="0xabc")]

    async def best_pair(self, profile):
        self.best_pair_calls += 1
        return self.pair


class MultiDiscoveryProvider:
    def __init__(self, pairs: list[DexPair]):
        self.pairs = {pair.token_address: pair for pair in pairs}

    async def latest_profiles(self):
        return [
            DexTokenProfile(chain=pair.chain, address=pair.token_address)
            for pair in self.pairs.values()
        ]

    async def best_pair(self, profile):
        return self.pairs.get(profile.address)


class FakeSender:
    def __init__(self):
        self.messages = []

    async def send(self, topic_id: int, text: str) -> bool:
        self.messages.append((topic_id, text))
        return True


class FakeRiskProvider:
    def __init__(self, report: RiskReport):
        self.report = report
        self.calls = []

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        self.calls.append((chain, address))
        return self.report


class SequenceRiskProvider:
    def __init__(self, reports):
        self.reports = list(reports)
        self.calls = []

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        self.calls.append((chain, address))
        if len(self.reports) > 1:
            return self.reports.pop(0)
        return self.reports[0]


class FakeWalletPerformanceProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    async def best_wallets_for_token(self, *, chain, token_address, token_symbol, periods):
        self.calls.append((chain, token_address, token_symbol, periods))
        return self.candidates


@pytest.mark.asyncio
async def test_live_signal_worker_sends_low_mc_profile_to_configured_topic():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xabc",
        symbol="BASE",
        name="Base Token",
        url="https://dexscreener.com/base/0xabc",
        market_cap_usd=250_000,
        liquidity_usd=20_000,
        volume_24h_usd=100_000,
        buys_5m=8,
        buys_1h=50,
        buys_24h=200,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "123",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "2",
                "V2_SIGNAL_MIN_QUALITY": "70",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert sent[0].topic_env_key == "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"
    assert sender.messages[0][0] == 123
    assert "V2 BASE Low Mc Freshies" in sender.messages[0][1]


@pytest.mark.asyncio
async def test_live_signal_worker_emits_best_real_candidate_per_configured_topic():
    now = datetime.now(timezone.utc)
    pairs = [
        DexPair(
            chain=Chain.ETHEREUM,
            token_address="0xethbig",
            symbol="EBIG",
            name="ETH Big",
            url=None,
            market_cap_usd=2_000_000,
            liquidity_usd=120_000,
            volume_24h_usd=260_000,
            buys_5m=30,
            buys_1h=180,
            buys_24h=600,
            pair_created_at=now - timedelta(minutes=30),
        ),
        DexPair(
            chain=Chain.ETHEREUM,
            token_address="0xethlow",
            symbol="ELOW",
            name="ETH Low",
            url=None,
            market_cap_usd=250_000,
            liquidity_usd=60_000,
            volume_24h_usd=160_000,
            buys_5m=12,
            buys_1h=80,
            buys_24h=240,
            pair_created_at=now - timedelta(minutes=40),
        ),
        DexPair(
            chain=Chain.BASE,
            token_address="0xbaselow",
            symbol="BLOW",
            name="Base Low",
            url=None,
            market_cap_usd=180_000,
            liquidity_usd=70_000,
            volume_24h_usd=180_000,
            buys_5m=18,
            buys_1h=90,
            buys_24h=260,
            pair_created_at=now - timedelta(minutes=25),
        ),
        DexPair(
            chain=Chain.BSC,
            token_address="0xbnbbig",
            symbol="BBIG",
            name="BNB Big",
            url=None,
            market_cap_usd=3_000_000,
            liquidity_usd=130_000,
            volume_24h_usd=280_000,
            buys_5m=28,
            buys_1h=170,
            buys_24h=550,
            pair_created_at=now - timedelta(minutes=35),
        ),
        DexPair(
            chain=Chain.BSC,
            token_address="0xbnblow",
            symbol="BLOW",
            name="BNB Low",
            url=None,
            market_cap_usd=200_000,
            liquidity_usd=55_000,
            volume_24h_usd=140_000,
            buys_5m=11,
            buys_1h=75,
            buys_24h=230,
            pair_created_at=now - timedelta(minutes=45),
        ),
    ]
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_ETH_FRESHIES_TOPIC_ID": "101",
                "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID": "102",
                "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID": "103",
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "202",
                "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "203",
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "302",
                "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID": "303",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "9",
            }
        ),
        provider=MultiDiscoveryProvider(pairs),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    sent_topics = {signal.topic_env_key for signal in sent}
    assert sent_topics == {
        "TELEGRAM_ETH_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
        "TELEGRAM_BNB_FRESHIES_TOPIC_ID",
        "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID",
    }
    assert {topic_id for topic_id, _ in sender.messages} == {101, 102, 103, 201, 202, 203, 301, 302, 303}
    assert worker.stats.alerts_by_topic["TELEGRAM_BASE_DEPLOYS_TOPIC_ID"] == 1
    assert worker.stats.candidates_by_topic["TELEGRAM_ETH_FRESHIES_TOPIC_ID"] >= 1


@pytest.mark.asyncio
async def test_live_signal_worker_dedupes_repeated_profiles():
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0xabc",
        symbol="BNB",
        name="BNB Token",
        url=None,
        market_cap_usd=5_000_000,
        liquidity_usd=50_000,
        volume_24h_usd=90_000,
        buys_5m=8,
        buys_1h=70,
        buys_24h=220,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env({"TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "456"}),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    assert len(await worker.run_once()) == 1
    assert await worker.run_once() == []
    assert len(sender.messages) == 1
    assert worker.stats.deduped == 1


@pytest.mark.asyncio
async def test_live_signal_worker_skips_unconfigured_topic():
    pair = DexPair(
        chain=Chain.ETHEREUM,
        token_address="0xabc",
        symbol="ETH",
        name="ETH Token",
        url=None,
        market_cap_usd=200_000,
        liquidity_usd=20_000,
        volume_24h_usd=90_000,
        buys_5m=8,
        buys_1h=70,
        buys_24h=220,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings(),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    assert await worker.run_once() == []
    assert sender.messages == []


@pytest.mark.asyncio
async def test_live_signal_worker_enforces_daily_cap():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xabc",
        symbol="CAP",
        name="Cap Token",
        url=None,
        market_cap_usd=200_000,
        liquidity_usd=20_000,
        volume_24h_usd=90_000,
        buys_5m=8,
        buys_1h=70,
        buys_24h=220,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "123",
                "V2_SIGNAL_DAILY_CAP": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    assert len(await worker.run_once()) == 1
    worker._sent_keys.clear()
    assert await worker.run_once() == []
    assert worker.stats.daily_sent == 1
    assert len(sender.messages) == 1


@pytest.mark.asyncio
async def test_live_signal_worker_enforces_topic_cap_without_starving_other_topics():
    now = datetime.now(timezone.utc)
    pairs = [
        DexPair(
            chain=Chain.BSC,
            token_address="0xbnbone",
            symbol="BONE",
            name="BNB One",
            url=None,
            market_cap_usd=250_000,
            liquidity_usd=120_000,
            volume_24h_usd=260_000,
            buys_5m=30,
            buys_1h=180,
            buys_24h=600,
            pair_created_at=now - timedelta(minutes=30),
        ),
        DexPair(
            chain=Chain.BASE,
            token_address="0xbaseone",
            symbol="BASE",
            name="Base One",
            url=None,
            market_cap_usd=250_000,
            liquidity_usd=120_000,
            volume_24h_usd=260_000,
            buys_5m=30,
            buys_1h=180,
            buys_24h=600,
            pair_created_at=now - timedelta(minutes=30),
        ),
    ]
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "302",
                "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "203",
                "V2_SIGNAL_DAILY_CAP": "0",
                "V2_SIGNAL_TOPIC_DAILY_CAP": "1",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "2",
            }
        ),
        provider=MultiDiscoveryProvider(pairs),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    first_cycle = await worker.run_once()
    worker._sent_keys.clear()
    second_cycle = await worker.run_once()

    assert {signal.topic_env_key for signal in first_cycle} == {
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
        "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID",
    }
    assert second_cycle == []
    assert worker.stats.rejected_budget_by_topic["TELEGRAM_BASE_DEPLOYS_TOPIC_ID"] >= 1
    assert worker.stats.rejected_budget_by_topic["TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID"] >= 1


@pytest.mark.asyncio
async def test_live_signal_worker_spends_daily_cap_on_highest_quality_candidates_first():
    now = datetime.now(timezone.utc)
    pairs = [
        DexPair(
            chain=Chain.ETHEREUM,
            token_address="0xstandard",
            symbol="STD",
            name="Standard Signal",
            url=None,
            market_cap_usd=1_000_000,
            liquidity_usd=50_000,
            volume_24h_usd=80_000,
            buys_5m=10,
            buys_1h=60,
            buys_24h=220,
            pair_created_at=now - timedelta(minutes=30),
        ),
        DexPair(
            chain=Chain.BASE,
            token_address="0xhigh",
            symbol="HIGH",
            name="High Signal",
            url=None,
            market_cap_usd=1_000_000,
            liquidity_usd=100_000,
            volume_24h_usd=160_000,
            buys_5m=10,
            buys_1h=60,
            buys_24h=220,
            pair_created_at=now - timedelta(minutes=30),
        ),
        DexPair(
            chain=Chain.BSC,
            token_address="0xelite",
            symbol="ELITE",
            name="Elite Signal",
            url=None,
            market_cap_usd=250_000,
            liquidity_usd=120_000,
            volume_24h_usd=260_000,
            buys_5m=30,
            buys_1h=180,
            buys_24h=600,
            pair_created_at=now - timedelta(minutes=30),
        ),
    ]
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_ETH_FRESHIES_TOPIC_ID": "101",
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
                "V2_SIGNAL_DAILY_CAP": "2",
            }
        ),
        provider=MultiDiscoveryProvider(pairs),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert [signal.symbol for signal in sent] == ["ELITE", "HIGH"]
    assert [topic_id for topic_id, _ in sender.messages] == [301, 201]
    assert worker.stats.daily_sent == 2


@pytest.mark.asyncio
async def test_live_signal_worker_copies_risk_checked_elite_signal_to_best_topic():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xelite",
        symbol="ELITE",
        name="Elite Token",
        url="https://dexscreener.com/base/0xelite",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID": "901",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
        best_signal_router=BestSignalRouter(daily_cap=7, min_score=95),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert [topic_id for topic_id, _ in sender.messages] == [201, 999]
    assert "Best Signal" in sender.messages[1][1]


@pytest.mark.asyncio
async def test_live_signal_worker_default_best_feed_waits_for_independent_confluence():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xstrong",
        symbol="STRONG",
        name="Strong Token",
        url="https://dexscreener.com/base/0xstrong",
        market_cap_usd=250_000,
        liquidity_usd=100_000,
        volume_24h_usd=220_000,
        buys_5m=25,
        buys_1h=130,
        buys_24h=500,
        pair_created_at=datetime.now(timezone.utc) - timedelta(hours=10),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert sent[0].quality_score >= 96
    assert [topic_id for topic_id, _ in sender.messages] == [201]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.pending_best_confluence == 1


@pytest.mark.asyncio
async def test_live_signal_worker_backtest_profile_blocks_best_copy_not_source_topic(tmp_path):
    performance_path = tmp_path / "best-performance.json"
    performance_path.write_text(
        json.dumps(
            {
                "v2_live": {
                    "sample_size": 50,
                    "hit_2x_rate": 0.08,
                    "rug_rate": 0.24,
                    "median_max_multiple": 1.05,
                    "average_max_multiple": 1.18,
                }
            }
        )
    )
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xprofileblocked",
        symbol="PROFILE",
        name="Profile Blocked",
        url="https://dexscreener.com/base/0xprofileblocked",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
                "BEST_SIGNAL_PERFORMANCE_PATH": str(performance_path),
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert [topic_id for topic_id, _ in sender.messages] == [201]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.pending_best_confluence == 0
    assert worker.stats.as_dict()["best_signal_rejected_by_reason"]["backtest_hit_rate_too_low"] == 1


@pytest.mark.asyncio
async def test_live_signal_worker_blocks_best_copy_when_sell_flow_is_not_elite():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xnotbest",
        symbol="FLOW",
        name="Source Only Flow",
        url="https://dexscreener.com/base/0xnotbest",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        sells_5m=23,
        sells_1h=100,
        sells_24h=260,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
        best_signal_router=BestSignalRouter(daily_cap=0, min_score=95),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert sent[0].quality_score >= 95
    assert [topic_id for topic_id, _ in sender.messages] == [201]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.pending_best_confluence == 0
    assert worker.stats.as_dict()["best_signal_rejected_by_reason"]["sell_pressure_too_high"] == 1


@pytest.mark.asyncio
async def test_live_signal_worker_copies_elite_best_wallet_signal_to_best_topic():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xelite",
        symbol="ELITE",
        name="Elite Token",
        url="https://dexscreener.com/base/0xelite",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    wallet_provider = FakeWalletPerformanceProvider(
        [
            WalletPerformanceCandidate(
                chain="base",
                wallet_address="0x1111111111111111111111111111111111111111",
                period="week",
                realized_pnl_usd=80_000,
                roi_pct=900,
                win_rate=0.9,
                trades=24,
                wins=22,
                losses=2,
                top_tokens=("ELITE",),
                evidence_url="https://deep-index.moralis.io",
            ),
            WalletPerformanceCandidate(
                chain="base",
                wallet_address="0x2222222222222222222222222222222222222222",
                period="week",
                realized_pnl_usd=70_000,
                roi_pct=760,
                win_rate=0.84,
                trades=20,
                wins=17,
                losses=3,
                top_tokens=("ELITE",),
                evidence_url="https://deep-index.moralis.io",
            )
        ]
    )
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID": "901",
                "TELEGRAM_BEST_WALLET_CONFLUENCE_TOPIC_ID": "902",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
        best_signal_router=BestSignalRouter(
            daily_cap=0,
            min_score=95,
            min_confluence_sources=2,
        ),
        wallet_performance_provider=wallet_provider,
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert wallet_provider.calls == [(Chain.BASE, "0xelite", "ELITE", ("week", "month", "year"))]
    assert [topic_id for topic_id, _ in sender.messages] == [201, 901, 999]
    assert "Best Wallet Coin BASE Week" in sender.messages[1][1]
    assert "0xelite" in sender.messages[1][1]
    assert "0x1111111111111111111111111111111111111111" not in sender.messages[1][1]
    assert "0x2222222222222222222222222222222222222222" not in sender.messages[1][1]
    assert "Confluence: Market structure + Best-wallet buys" in sender.messages[2][1]
    assert worker.stats.best_wallet_signals_sent == 1


@pytest.mark.asyncio
async def test_live_signal_worker_counts_wallet_provider_empty_and_rejected_periods():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xwalletquiet",
        symbol="QUIET",
        name="Quiet Wallet Token",
        url="https://dexscreener.com/base/0xwalletquiet",
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    wallet_provider = FakeWalletPerformanceProvider(
        [
            WalletPerformanceCandidate(
                chain="base",
                wallet_address="0x1111111111111111111111111111111111111111",
                period="week",
                realized_pnl_usd=20_000,
                roi_pct=400,
                win_rate=0.9,
                trades=10,
                wins=9,
                losses=1,
                top_tokens=("QUIET",),
                evidence_url="https://deep-index.moralis.io",
            )
        ]
    )
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID": "901",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["Honeypot.is simulation passed"])),
        wallet_performance_provider=wallet_provider,
    )

    await worker.run_once()

    assert worker.stats.best_wallet_tokens_checked == 1
    assert worker.stats.best_wallet_candidates_by_period["week"] == 1
    assert worker.stats.best_wallet_rejected_by_period["week"] == 1
    assert worker.stats.best_wallet_rejected_by_reason["week:not_enough_profitable_wallets"] == 1
    assert worker.stats.best_wallet_last_score_by_period["week"] == 0
    assert worker.stats.best_wallet_signals_sent == 0


@pytest.mark.asyncio
async def test_live_signal_worker_reports_disabled_topics_separately_from_active_topic_candidates():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xbaselow",
        symbol="BLOW",
        name="Base Low",
        url=None,
        market_cap_usd=180_000,
        liquidity_usd=70_000,
        volume_24h_usd=180_000,
        buys_5m=18,
        buys_1h=90,
        buys_24h=260,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=25),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "203",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["Honeypot.is simulation passed"])),
    )

    sent = await worker.run_once()

    assert {signal.topic_env_key for signal in sent} == {
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
    }
    assert "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID" not in worker.stats.candidates_by_topic
    assert worker.stats.skipped_unconfigured_by_topic["TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"] == 1


@pytest.mark.asyncio
async def test_live_signal_worker_does_not_copy_risky_signal_to_best_topic():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xtrap",
        symbol="TRAP",
        name="Trap Token",
        url=None,
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.CRITICAL, is_honeypot=True)),
        best_signal_router=BestSignalRouter(daily_cap=7, min_score=95),
    )

    assert await worker.run_once() == []
    assert sender.messages == []


@pytest.mark.asyncio
async def test_live_signal_worker_sends_unindexed_medium_risk_to_source_topic_only():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xunindexed",
        symbol="INDEX",
        name="Unindexed Token",
        url=None,
        market_cap_usd=250_000,
        liquidity_usd=120_000,
        volume_24h_usd=260_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(level=RiskLevel.MEDIUM, reasons=["holder data missing or zero holders reported"])
        ),
        best_signal_router=BestSignalRouter(daily_cap=0, min_score=95),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert [topic_id for topic_id, _ in sender.messages] == [201]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.pending_best_confluence == 0


@pytest.mark.asyncio
async def test_live_signal_worker_sends_elite_provider_gap_to_source_topic_only():
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0xprovidergap",
        symbol="GAP",
        name="Provider Gap",
        url=None,
        market_cap_usd=450_000,
        liquidity_usd=150_000,
        volume_24h_usd=420_000,
        buys_5m=45,
        buys_1h=240,
        buys_24h=900,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.MEDIUM,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=[
                    "holder data missing or zero holders reported",
                    "Honeypot.is unavailable: Client error '404 Not Found'",
                ],
            )
        ),
        best_signal_router=BestSignalRouter(daily_cap=0, min_score=95),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert sent[0].topic_env_key == "TELEGRAM_BNB_FRESHIES_TOPIC_ID"
    assert sent[0].risk_level is RiskLevel.MEDIUM
    assert [topic_id for topic_id, _ in sender.messages] == [301]
    assert worker.stats.best_signals_sent == 0


@pytest.mark.asyncio
async def test_live_signal_worker_rechecks_provider_gap_for_delayed_best_signal():
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0xdelayedbest",
        symbol="DELAY",
        name="Delayed Best",
        url="https://dexscreener.com/bsc/0xdelayedbest",
        market_cap_usd=450_000,
        liquidity_usd=150_000,
        volume_24h_usd=420_000,
        buys_5m=45,
        buys_1h=240,
        buys_24h=900,
        sells_5m=10,
        sells_1h=40,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sender = FakeSender()
    risk_provider = SequenceRiskProvider(
        [
            RiskReport(
                level=RiskLevel.MEDIUM,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=[
                    "holder data missing or zero holders reported",
                    "Honeypot.is unavailable: Client error '404 Not Found'",
                ],
            ),
            RiskReport(
                level=RiskLevel.MEDIUM,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=[
                    "holder data missing or zero holders reported",
                    "Honeypot.is unavailable: Client error '404 Not Found'",
                ],
            ),
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["GoPlus found no high-risk flags"],
            ),
        ]
    )
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=risk_provider,
        best_signal_router=BestSignalRouter(daily_cap=0, min_score=95),
    )

    first_sent = await worker.run_once()
    second_sent = await worker.run_once()

    assert len(first_sent) == 1
    assert second_sent == []
    assert [topic_id for topic_id, _ in sender.messages] == [301, 999]
    assert "Best Signal" in sender.messages[1][1]
    assert worker.stats.best_signals_sent == 1
    assert worker.stats.as_dict()["best_signal_skipped_by_reason"]["risk_not_low"] == 1
    assert worker.stats.as_dict()["pending_best_signal_rechecks"] == 0


@pytest.mark.asyncio
async def test_live_signal_worker_rejects_weak_latest_profile():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xweak",
        symbol="WEAK",
        name="Weak Token",
        url=None,
        market_cap_usd=8_000,
        liquidity_usd=2_000,
        volume_24h_usd=5_000,
        buys_5m=1,
        buys_1h=4,
        buys_24h=8,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env({"TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "123"}),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["Honeypot.is simulation passed"])),
    )

    assert await worker.run_once() == []
    assert sender.messages == []
    assert worker.stats.rejected_low_quality == 1
    assert worker.stats.rejected_low_quality_by_reason["liquidity_too_low"] == 1
    assert worker.stats.as_dict()["last_low_quality_rejections"][-1] == {
        "chain": "base",
        "symbol": "WEAK",
        "address": "0xweak",
        "reason": "liquidity_too_low",
    }


@pytest.mark.asyncio
async def test_live_signal_worker_rejects_rug_like_selloff_even_with_large_volume():
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0x8aa4e31d599bba7b3f5977e7d157cd899129538b",
        symbol="RUG",
        name="Rug Like Token",
        url="https://www.geckoterminal.com/bsc/pools/0x888e2d39bab6a25bdf401d2037c4d91e04c2f1ff",
        market_cap_usd=300_000,
        liquidity_usd=46_822,
        volume_24h_usd=484_353,
        buys_5m=80,
        buys_1h=387,
        buys_24h=387,
        sells_5m=120,
        sells_1h=530,
        sells_24h=530,
        price_change_5m=-22,
        price_change_1h=-99.9,
        price_change_24h=-99.9,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=27),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env({"TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "123"}),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["Honeypot.is simulation passed"])),
    )

    assert await worker.run_once() == []
    assert sender.messages == []
    assert worker.stats.rejected_low_quality == 1


@pytest.mark.asyncio
async def test_live_signal_worker_allows_older_pairs_when_current_activity_is_strong():
    pair = DexPair(
        chain=Chain.ETHEREUM,
        token_address="0xactive",
        symbol="ACTIVE",
        name="Active Older Pair",
        url=None,
        market_cap_usd=300_000,
        liquidity_usd=120_000,
        volume_24h_usd=250_000,
        buys_5m=10,
        buys_1h=180,
        buys_24h=1_500,
        pair_created_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_ETH_FRESHIES_TOPIC_ID": "101",
                "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID": "102",
                "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID": "103",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["Honeypot.is simulation passed"])),
    )

    sent = await worker.run_once()

    assert {signal.topic_env_key for signal in sent} == {
        "TELEGRAM_ETH_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID",
    }


@pytest.mark.asyncio
async def test_live_signal_worker_blocks_honeypot_before_sending():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xtrap",
        symbol="TRAP",
        name="Trap Token",
        url=None,
        market_cap_usd=250_000,
        liquidity_usd=80_000,
        volume_24h_usd=220_000,
        buys_5m=20,
        buys_1h=120,
        buys_24h=500,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sender = FakeSender()
    risk_provider = FakeRiskProvider(
        RiskReport(
            level=RiskLevel.CRITICAL,
            is_honeypot=True,
            sell_tax_bps=9900,
            reasons=["honeypot simulation failed"],
        )
    )
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "202",
                "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "203",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
                "V2_SIGNAL_MIN_QUALITY": "70",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=risk_provider,
    )

    assert await worker.run_once() == []
    assert sender.messages == []
    assert worker.stats.rejected_risk == 3
    assert worker.stats.rejected_risk_by_topic_reason == {
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID:honeypot": 1,
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID:honeypot": 1,
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID:honeypot": 1,
    }
    assert risk_provider.calls == [(Chain.BASE, "0xtrap")]


@pytest.mark.asyncio
async def test_live_signal_worker_blocks_unknown_risk_provider_state():
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0xunknown",
        symbol="UNK",
        name="Unknown Risk",
        url=None,
        market_cap_usd=300_000,
        liquidity_usd=90_000,
        volume_24h_usd=240_000,
        buys_5m=20,
        buys_1h=120,
        buys_24h=500,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": "302",
                "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID": "303",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
                "V2_SIGNAL_MIN_QUALITY": "70",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.MEDIUM, reasons=["Honeypot.is rate limited"])),
    )

    assert await worker.run_once() == []
    assert sender.messages == []
    assert worker.stats.rejected_risk == 3
    assert worker.stats.rejected_risk_by_topic_reason == {
        "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID:provider_unavailable": 1,
        "TELEGRAM_BNB_FRESHIES_TOPIC_ID:provider_unavailable": 1,
        "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID:provider_unavailable": 1,
    }
    stats = worker.stats.as_dict()
    assert {
        sample["topic_env_key"] for sample in stats["last_risk_rejections"]
    } == {
        "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_BNB_FRESHIES_TOPIC_ID",
        "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID",
    }
    assert all(
        sample["chain"] == "bsc"
        and sample["symbol"] == "UNK"
        and sample["address"] == "0xunknown"
        and sample["reason"] == "provider_unavailable"
        and sample["risk_level"] == "medium"
        and sample["risk_reasons"] == ["Honeypot.is rate limited"]
        for sample in stats["last_risk_rejections"]
    )


@pytest.mark.asyncio
async def test_live_signal_worker_blocks_elite_base_source_signal_with_unlocked_liquidity_risk():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xbasewatch",
        symbol="WATCH",
        name="Base Watch",
        url=None,
        market_cap_usd=120_000,
        liquidity_usd=80_000,
        volume_24h_usd=220_000,
        buys_5m=25,
        buys_1h=150,
        buys_24h=500,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "202",
                "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": "203",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "3",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.HIGH,
                liquidity_pull_risk=True,
                reasons=["Honeypot.is simulation passed", "liquidity is not locked"],
            )
        ),
    )

    sent = await worker.run_once()

    assert sent == []
    assert sender.messages == []
    assert worker.stats.rejected_risk == 3
    assert worker.stats.rejected_risk_by_topic_reason == {
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID:liquidity_pull_risk": 1,
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID:liquidity_pull_risk": 1,
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID:liquidity_pull_risk": 1,
    }
    assert worker.stats.best_signals_sent == 0


@pytest.mark.asyncio
async def test_live_signal_worker_journals_successful_source_alert(tmp_path):
    journal_path = tmp_path / "v2-signals.jsonl"
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xjournal",
        symbol="JOURNAL",
        name="Journal Token",
        url="https://dexscreener.com/base/0xjournal",
        price_usd=0.0025,
        market_cap_usd=180_000,
        liquidity_usd=90_000,
        volume_24h_usd=240_000,
        buys_5m=24,
        buys_1h=160,
        buys_24h=700,
        sells_5m=4,
        sells_1h=35,
        sells_24h=220,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=35),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "202",
                "V2_SIGNAL_JOURNAL_PATH": str(journal_path),
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=100,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    record = json.loads(journal_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["token_address"] == "0xjournal"
    assert record["price_usd"] == 0.0025
    assert record["quality_score"] == sent[0].quality_score
    assert record["risk_text"] == "low | Tax B/S: 0.0%/1.0% | Honeypot.is simulation passed"
    assert worker.stats.journal_records_written == 1
    assert worker.stats.journal_last_error is None

@pytest.mark.asyncio
async def test_live_signal_worker_routes_elite_robinhood_candidate_to_source_only_without_verified_risk():
    pair = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0x1111111111111111111111111111111111111111",
        symbol="EARLY",
        name="Early Robinhood Token",
        url="https://dexscreener.com/robinhood/0xpair",
        market_cap_usd=1_819_152,
        liquidity_usd=135_145,
        volume_24h_usd=4_079_521,
        buys_5m=57,
        buys_1h=960,
        buys_24h=3_000,
        sells_5m=21,
        sells_1h=332,
        sells_24h=1_000,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=693),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_RH_FRESHIES_TOPIC_ID": "4663",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.MEDIUM,
                reasons=["Robinhood Chain independent security indexers unavailable"],
            )
        ),
        best_signal_router=BestSignalRouter(daily_cap=0, min_score=95),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert sent[0].chain is Chain.ROBINHOOD
    assert sent[0].quality_score == 91
    assert sent[0].risk_level is RiskLevel.MEDIUM
    assert [topic_id for topic_id, _ in sender.messages] == [4663]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.best_signal_skipped_by_reason["risk_not_low"] == 1

def test_live_signal_worker_classifies_robinhood_candidates_into_one_distinct_topic():
    now = datetime.now(timezone.utc)
    worker = LiveSignalWorker(
        settings=V2Settings.from_env({}),
        provider=FakeDiscoveryProvider(None),
        sender=None,
        risk_provider=FakeRiskProvider(RiskReport(level=RiskLevel.LOW, reasons=["passed"])),
    )

    low_mc = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0xlow",
        symbol="LOW",
        name="Low Cap",
        url=None,
        market_cap_usd=250_000,
        liquidity_usd=100_000,
        volume_24h_usd=300_000,
        buys_5m=30,
        buys_1h=300,
        buys_24h=700,
        sells_5m=8,
        sells_1h=70,
        sells_24h=250,
        pair_created_at=now - timedelta(minutes=60),
    )
    big_flow = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0xbig",
        symbol="BIG",
        name="Large Flow",
        url=None,
        market_cap_usd=2_000_000,
        liquidity_usd=250_000,
        volume_24h_usd=1_500_000,
        buys_5m=80,
        buys_1h=1_200,
        buys_24h=3_000,
        sells_5m=30,
        sells_1h=500,
        sells_24h=1_200,
        pair_created_at=now - timedelta(minutes=90),
    )
    fresh_deploy = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0xdeploy",
        symbol="DEPLOY",
        name="New Pair",
        url=None,
        market_cap_usd=2_000_000,
        liquidity_usd=110_000,
        volume_24h_usd=300_000,
        buys_5m=25,
        buys_1h=300,
        buys_24h=900,
        sells_5m=8,
        sells_1h=90,
        sells_24h=300,
        pair_created_at=now - timedelta(hours=2),
    )
    standard_freshie = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0xfresh",
        symbol="FRESH",
        name="Standard Freshie",
        url=None,
        market_cap_usd=1_200_000,
        liquidity_usd=100_000,
        volume_24h_usd=300_000,
        buys_5m=25,
        buys_1h=300,
        buys_24h=900,
        sells_5m=8,
        sells_1h=90,
        sells_24h=300,
        pair_created_at=now - timedelta(hours=10),
    )

    classifications = {
        pair.symbol: worker._signals_from_pair(pair)
        for pair in (low_mc, big_flow, fresh_deploy, standard_freshie)
    }

    assert {symbol: len(signals) for symbol, signals in classifications.items()} == {
        "LOW": 1,
        "BIG": 1,
        "DEPLOY": 1,
        "FRESH": 1,
    }
    assert classifications["LOW"][0].feature is TopicFeature.LOW_MC_FRESHIES
    assert classifications["BIG"][0].feature is TopicFeature.BIG_FRESHIES
    assert classifications["DEPLOY"][0].feature is TopicFeature.DEPLOYS
    assert classifications["FRESH"][0].feature is TopicFeature.FRESHIES


@pytest.mark.asyncio
async def test_live_signal_worker_hydrates_recent_journal_dedupe_after_restart(tmp_path):
    pair = DexPair(
        chain=Chain.ROBINHOOD,
        token_address="0xabc",
        symbol="RESTART",
        name="Restart Safe",
        url="https://dexscreener.com/robinhood/0xpair",
        market_cap_usd=250_000,
        liquidity_usd=150_000,
        volume_24h_usd=420_000,
        buys_5m=45,
        buys_1h=240,
        buys_24h=900,
        sells_5m=10,
        sells_1h=40,
        sells_24h=200,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    env = {
        "TELEGRAM_RH_LOW_MC_FRESHIES_TOPIC_ID": "4663",
        "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
        "V2_SIGNAL_JOURNAL_PATH": str(tmp_path / "signals.jsonl"),
    }
    risk = FakeRiskProvider(
        RiskReport(level=RiskLevel.LOW, reasons=["canonical Robinhood Chain token"])
    )
    first_sender = FakeSender()
    first = LiveSignalWorker(
        settings=V2Settings.from_env(env),
        provider=FakeDiscoveryProvider(pair),
        sender=first_sender,
        risk_provider=risk,
    )

    assert len(await first.run_once()) == 1

    second_sender = FakeSender()
    restarted = LiveSignalWorker(
        settings=V2Settings.from_env(env),
        provider=FakeDiscoveryProvider(pair),
        sender=second_sender,
        risk_provider=risk,
    )

    assert await restarted.run_once() == []
    assert second_sender.messages == []
    assert restarted.stats.hydrated_dedupe_keys == 1


@pytest.mark.asyncio
async def test_live_signal_worker_keeps_unconfirmed_cz_style_reversal_out_of_best_feed(tmp_path):
    journal_path = tmp_path / "v2-signals.jsonl"
    pair = DexPair(
        chain=Chain.BSC,
        token_address="0x7A848a5A8169aa6a2f603D056A749f924F504444",
        symbol="CZ",
        name="The Final Form Bull",
        url="https://dexscreener.com/bsc/0xd55fa2c5e63ecac3a158ca3fed4c8c2185ed45b2",
        price_usd=0.006648,
        market_cap_usd=6_648_750,
        liquidity_usd=353_378.22,
        volume_24h_usd=1_751_390.77,
        buys_5m=33,
        buys_1h=567,
        buys_24h=5_976,
        sells_5m=11,
        sells_1h=302,
        sells_24h=5_046,
        price_change_5m=-1.32,
        price_change_1h=-7.67,
        price_change_24h=-32.23,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=12_021),
    )
    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "301",
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID": "999",
                "V2_SIGNAL_JOURNAL_PATH": str(journal_path),
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["GoPlus found no high-risk flags"],
            )
        ),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert sent[0].quality_score == 85
    assert [topic_id for topic_id, _ in sender.messages] == [301]
    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record.get("record_type") for record in records] == ["source_signal_sent"]
    assert worker.stats.best_signals_sent == 0
    assert worker.stats.pending_best_confluence == 1
    assert worker.stats.best_signal_journal_records_written == 0
    assert worker.stats.best_signal_journal_last_error is None
class ThrowingSender:
    def __init__(self, failing_topic_id: int):
        self.failing_topic_id = failing_topic_id
        self.messages = []

    async def send(self, topic_id: int, text: str) -> bool:
        self.messages.append((topic_id, text))
        if topic_id == self.failing_topic_id:
            raise RuntimeError("message thread not found")
        return True


@pytest.mark.asyncio
async def test_live_signal_worker_isolates_failed_sender_calls_and_continues_later_topics():
    pair = DexPair(
        chain=Chain.ETHEREUM,
        token_address="0xdeliveryfailure",
        symbol="ETHOK",
        name="Ethereum Token",
        url="https://dexscreener.com/ethereum/0xdeliveryfailure",
        market_cap_usd=1_000_000,
        liquidity_usd=100_000,
        volume_24h_usd=250_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    sender = ThrowingSender(failing_topic_id=102)
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_ETH_FRESHIES_TOPIC_ID": "101",
                "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID": "102",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "2",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert [topic_id for topic_id, _ in sender.messages] == [102, 101]
    assert [signal.topic_env_key for signal in sent] == ["TELEGRAM_ETH_FRESHIES_TOPIC_ID"]
    assert worker.stats.delivery_failures_by_topic == {"TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID": 1}
    assert worker._topic_budgets["TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID"].sent_count(
        now=worker.stats.last_run_at
    ) == 0



@pytest.mark.asyncio
async def test_live_signal_worker_continues_after_individual_pair_lookup_failure():
    healthy_pair = DexPair(
        chain=Chain.BASE,
        token_address="0xhealthy",
        symbol="HEALTHY",
        name="Healthy Base Token",
        url="https://dexscreener.com/base/0xhealthy",
        market_cap_usd=1_000_000,
        liquidity_usd=100_000,
        volume_24h_usd=250_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )

    class PartiallyFailingDiscoveryProvider:
        async def latest_profiles(self):
            return [
                DexTokenProfile(chain=Chain.BASE, address="0xfailing"),
                DexTokenProfile(chain=Chain.BASE, address="0xhealthy"),
            ]

        async def best_pair(self, profile):
            if profile.address == "0xfailing":
                raise RuntimeError("DexScreener token lookup timed out")
            return healthy_pair

    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "1",
            }
        ),
        provider=PartiallyFailingDiscoveryProvider(),
        sender=sender,
        risk_provider=FakeRiskProvider(
            RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )
        ),
    )

    sent = await worker.run_once()

    assert [signal.token_address for signal in sent] == ["0xhealthy"]
    assert [topic_id for topic_id, _ in sender.messages] == [201]
    assert worker.stats.pair_lookup_failures == 1

@pytest.mark.asyncio
async def test_live_signal_worker_continues_after_transient_risk_lookup_failure():
    pair = DexPair(
        chain=Chain.BASE,
        token_address="0xriskretry",
        symbol="RISK",
        name="Risk Retry Token",
        url="https://dexscreener.com/base/0xriskretry",
        market_cap_usd=250_000,
        liquidity_usd=100_000,
        volume_24h_usd=250_000,
        buys_5m=30,
        buys_1h=180,
        buys_24h=600,
        pair_created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )

    class FailOnceRiskProvider:
        def __init__(self):
            self.calls = 0

        async def fetch_risk(self, chain, address):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("risk provider timed out")
            return RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["Honeypot.is simulation passed"],
            )

    sender = FakeSender()
    worker = LiveSignalWorker(
        settings=V2Settings.from_env(
            {
                "TELEGRAM_BASE_FRESHIES_TOPIC_ID": "201",
                "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "202",
                "V2_SIGNAL_MAX_ALERTS_PER_CYCLE": "2",
            }
        ),
        provider=FakeDiscoveryProvider(pair),
        sender=sender,
        risk_provider=FailOnceRiskProvider(),
    )

    sent = await worker.run_once()

    assert len(sent) == 1
    assert worker.stats.risk_lookup_failures == 1
    assert len(sender.messages) == 1