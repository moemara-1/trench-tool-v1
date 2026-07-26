from types import SimpleNamespace

import pytest

from services import solana_listener as solana_listener_module
from services.pumpportal_listener import PumpPortalEvent
from services.solana_listener import SolanaListener


class _TokenData:
    symbol = "EARLY"
    name = "Early Token"
    liquidity_usd = 8_000
    market_cap = 35_000
    mc_string = "$35K"


class _TokenFetcher:
    async def get_token_data(self, token_address):
        return _TokenData()


class _CreatorAnalyzer:
    def __init__(self):
        self.analyzed = []
        self.marked = []

    async def analyze_creator(self, wallet_address, current_token_address):
        self.analyzed.append((wallet_address, current_token_address))
        return SimpleNamespace(
            is_good_creator=True,
            successful_tokens=("previous-winner",),
            total_wallet_value_usd=42_000,
        )

    def check_is_good_creator(self, profile):
        return profile.is_good_creator and bool(profile.successful_tokens)

    def should_alert(self, wallet_address):
        return True

    async def format_good_creator_alert(self, **kwargs):
        return f"good-creator:{kwargs['contract_address']}"

    def mark_alerted(self, wallet_address):
        self.marked.append(wallet_address)

    def increment_alerts(self):
        return None


class _Verifier:
    MIN_LIQUIDITY_USD = 500
    MIN_MARKET_CAP_USD = 10_000

    def __init__(self):
        self.calls = []

    def verify_from_data(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(is_verified=True)


class _LateMigrationTracker:
    def __init__(self):
        self.alerts = 0

    async def check_late_bonding(self, token_address, program_ids):
        return SimpleNamespace(delay_hours=30)

    async def format_late_migration_alert(self, **kwargs):
        return f"late-migration:{kwargs['contract_address']}"

    def increment_alerts(self):
        self.alerts += 1


class _Telegram:
    def __init__(self):
        self.messages = []

    async def send_alert(self, message, topic_id=None):
        self.messages.append((message, topic_id))
        return 99


@pytest.mark.asyncio
async def test_pumpportal_new_token_sends_good_creator_only_after_real_creator_and_token_checks(monkeypatch):
    listener = object.__new__(SolanaListener)
    listener._launchpad_tokens = set()
    listener.creator_analyzer = _CreatorAnalyzer()
    listener.token_fetcher = _TokenFetcher()
    listener.token_verifier = _Verifier()
    listener.telegram = _Telegram()
    listener._creator_alerts_sent = 0
    monkeypatch.setattr(solana_listener_module.settings, "telegram_good_creator_topic_id", 321, raising=False)

    event = PumpPortalEvent(
        kind="new_token",
        mint="PumpMint111111111111111111111111111111111111",
        symbol="EARLY",
        name="Early Token",
        creator_wallet="Creator1111111111111111111111111111111111",
        signature="create-signature",
        initial_buy_sol=1.5,
        market_cap_sol=20.0,
        pool="pump",
    )

    await listener._handle_pumpportal_event(event)

    assert event.mint in listener._launchpad_tokens
    assert listener.creator_analyzer.analyzed == [(event.creator_wallet, event.mint)]
    assert listener.token_verifier.calls == [
        {
            "token_address": event.mint,
            "dex_name": "pump.fun",
            "liquidity_usd": 8_000,
            "market_cap": 35_000,
            "program_ids": ["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"],
        }
    ]
    assert listener.telegram.messages == [(f"good-creator:{event.mint}", 321)]
    assert listener._creator_alerts_sent == 1


@pytest.mark.asyncio
async def test_pumpportal_migration_sends_only_confirmed_late_migration(monkeypatch):
    listener = object.__new__(SolanaListener)
    listener.late_migration_tracker = _LateMigrationTracker()
    listener.token_fetcher = _TokenFetcher()
    listener.telegram = _Telegram()
    listener._late_migration_alerts_sent = 0
    monkeypatch.setattr(solana_listener_module.settings, "telegram_late_migration_topic_id", 654, raising=False)

    event = PumpPortalEvent(
        kind="migration",
        mint="PumpMint111111111111111111111111111111111111",
        symbol="EARLY",
        name="Early Token",
        creator_wallet=None,
        signature="migration-signature",
        initial_buy_sol=None,
        market_cap_sol=25.0,
        pool="raydium",
    )

    await listener._handle_pumpportal_event(event)

    assert listener.telegram.messages == [(f"late-migration:{event.mint}", 654)]
    assert listener.late_migration_tracker.alerts == 1
    assert listener._late_migration_alerts_sent == 1