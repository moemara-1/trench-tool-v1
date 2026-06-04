from datetime import datetime, timedelta

import pytest

from services.solana_listener import SolanaListener


class _FakeQueue:
    def qsize(self) -> int:
        return 7


def test_solana_listener_backup_poll_runs_when_websocket_has_no_recent_activity():
    listener = object.__new__(SolanaListener)
    listener._ws_connected = True
    listener._last_ws_connected_at = datetime.utcnow() - timedelta(minutes=10)
    listener._last_tx_received_at = None

    assert listener._should_backup_poll(now=datetime.utcnow()) is True


def test_solana_listener_backup_poll_stays_on_standby_for_fresh_websocket_activity():
    listener = object.__new__(SolanaListener)
    listener._ws_connected = True
    listener._last_ws_connected_at = datetime.utcnow() - timedelta(minutes=10)
    listener._last_tx_received_at = datetime.utcnow() - timedelta(seconds=30)

    assert listener._should_backup_poll(now=datetime.utcnow()) is False


def test_solana_listener_stats_expose_websocket_and_queue_liveness():
    listener = object.__new__(SolanaListener)
    listener._tx_received = 4
    listener._tx_processed = 2
    listener._alerts_sent = 0
    listener._dormant_alerts_sent = 0
    listener._sns_alerts_sent = 0
    listener._vanish_alerts_sent = 0
    listener._bundle_alerts_sent = 0
    listener._late_migration_alerts_sent = 0
    listener._streamflow_alerts_sent = 0
    listener._dev_held_alerts_sent = 0
    listener._creator_alerts_sent = 0
    listener._socials_alerts_sent = 0
    listener._strong_launch_alerts_sent = 0
    listener._strongfloor_alerts_sent = 0
    listener._errors = 1
    listener._running = True
    listener._seen_tokens = {"token"}
    listener._ws_connected = True
    listener._last_ws_connected_at = datetime(2026, 1, 1, 12, 0, 0)
    listener._last_tx_received_at = datetime(2026, 1, 1, 12, 3, 0)
    listener._tx_queue = _FakeQueue()
    listener.sns_tracker = _Stats({"domains_cached": 1})
    listener.vanish_tracker = _Stats({"vanish_buys_tracked": 0})
    listener.bundle_detector = _Stats({"tracked_tokens": 2})
    listener.late_migration_tracker = _Stats({"pending_bondings": 0})
    listener.streamflow_tracker = _Stats({"tokens_with_locks": 0})
    listener.dev_held_tracker = _Stats({"tokens_tracked": 3})
    listener.creator_analyzer = _Stats({"creators_analyzed": 4})
    listener.socials_checker = _Stats({"tokens_checked": 5})
    listener.strong_launch_tracker = _Stats({"strong_launches": 6})
    listener.strongfloor_tracker = _Stats({"tokens_tracked": 7})
    listener.rpc_manager = _Stats({"total_endpoints": 8})

    stats = listener.get_stats()

    assert stats["websocket_connected"] is True
    assert stats["last_ws_connected_at"] == "2026-01-01T12:00:00"
    assert stats["last_tx_received_at"] == "2026-01-01T12:03:00"
    assert stats["queue_size"] == 7
    assert stats["modules"]["sns"]["domains_cached"] == 1
    assert stats["modules"]["socials"]["tokens_checked"] == 5
    assert stats["modules"]["strongfloor"]["tokens_tracked"] == 7
    assert stats["rpc"]["total_endpoints"] == 8


def test_solana_listener_captures_first_seen_before_format_marks_token_seen():
    listener = object.__new__(SolanaListener)
    listener._seen_tokens = set()

    first_seen = listener._capture_first_seen_for_enrichment("token")
    listener._seen_tokens.add("token")

    assert first_seen is True


class _Stats:
    def __init__(self, stats):
        self.stats = stats

    def get_stats(self):
        return self.stats


class _StreamflowTracker:
    def __init__(self):
        self.incremented = False
        self.parsed_tokens = []
        self.alerted_tokens = set()

    def is_streamflow_lock(self, program_ids):
        return "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m" in program_ids

    def should_alert_token(self, token_address):
        return token_address not in self.alerted_tokens

    def mark_alerted(self, token_address):
        self.alerted_tokens.add(token_address)

    def parse_lock_from_tx(self, tx_data, token_address):
        self.parsed_tokens.append(token_address)
        return type("Lock", (), {"lock_amount": 12345})()

    async def format_streamflow_alert(self, **kwargs):
        return f"streamflow:{kwargs['contract_address']}:{kwargs['lock_amount']}"

    def increment_alerts(self):
        self.incremented = True


class _TokenFetcher:
    async def get_token_data(self, token_address):
        return type(
            "TokenData",
            (),
            {
                "symbol": "LOCK",
                "name": "Locked Token",
                "mc_string": "$42K",
                "age_string": "12m",
            },
        )()


class _EmptyTokenFetcher:
    async def get_token_data(self, token_address):
        return None


class _Telegram:
    def __init__(self):
        self.messages = []

    async def send_alert(self, message, topic_id=None):
        self.messages.append((message, topic_id))
        return 99


def _streamflow_tx():
    return {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "wallet", "signer": True},
                    {
                        "pubkey": "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m",
                        "source": "program",
                    },
                ],
                "instructions": [
                    {"programId": "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m"}
                ],
            }
        },
        "meta": {
            "preTokenBalances": [
                {
                    "mint": "So11111111111111111111111111111111111111112",
                    "uiTokenAmount": {"uiAmount": 1},
                },
                {
                    "mint": "TokenMint111111111111111111111111111111111111",
                    "uiTokenAmount": {"uiAmount": 1000},
                },
            ],
            "postTokenBalances": [
                {
                    "mint": "TokenMint111111111111111111111111111111111111",
                    "uiTokenAmount": {"uiAmount": 900},
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_solana_listener_sends_direct_streamflow_lock(monkeypatch):
    listener = object.__new__(SolanaListener)
    listener.streamflow_tracker = _StreamflowTracker()
    listener.token_fetcher = _TokenFetcher()
    listener.telegram = _Telegram()
    listener._streamflow_alerts_sent = 0

    monkeypatch.setattr("services.solana_listener.settings.telegram_streamflow_topic_id", 1234)

    sent = await listener._maybe_process_streamflow_lock(_streamflow_tx())

    assert sent is True
    assert listener._streamflow_alerts_sent == 1
    assert listener.streamflow_tracker.incremented is True
    assert listener.streamflow_tracker.parsed_tokens == ["TokenMint111111111111111111111111111111111111"]
    assert listener.streamflow_tracker.alerted_tokens == {"TokenMint111111111111111111111111111111111111"}
    assert listener.telegram.messages == [
        ("streamflow:TokenMint111111111111111111111111111111111111:12345", 1234)
    ]


@pytest.mark.asyncio
async def test_solana_listener_skips_streamflow_lock_without_token_metadata(monkeypatch):
    listener = object.__new__(SolanaListener)
    listener.streamflow_tracker = _StreamflowTracker()
    listener.token_fetcher = _EmptyTokenFetcher()
    listener.telegram = _Telegram()
    listener._streamflow_alerts_sent = 0

    monkeypatch.setattr("services.solana_listener.settings.telegram_streamflow_topic_id", 1234)

    sent = await listener._maybe_process_streamflow_lock(_streamflow_tx())

    assert sent is False
    assert listener._streamflow_alerts_sent == 0
    assert listener.telegram.messages == []


@pytest.mark.asyncio
async def test_solana_listener_skips_duplicate_streamflow_token(monkeypatch):
    listener = object.__new__(SolanaListener)
    tracker = _StreamflowTracker()
    tracker.mark_alerted("TokenMint111111111111111111111111111111111111")
    listener.streamflow_tracker = tracker
    listener.token_fetcher = _TokenFetcher()
    listener.telegram = _Telegram()
    listener._streamflow_alerts_sent = 0

    monkeypatch.setattr("services.solana_listener.settings.telegram_streamflow_topic_id", 1234)

    sent = await listener._maybe_process_streamflow_lock(_streamflow_tx())

    assert sent is False
    assert listener._streamflow_alerts_sent == 0
    assert listener.telegram.messages == []
