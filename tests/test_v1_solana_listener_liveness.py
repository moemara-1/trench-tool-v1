import asyncio
from datetime import datetime, timedelta

import pytest

from services.sns_tracker import SNSTracker
from services.solana_listener import SolanaListener
from services.strongfloor_tracker import StrongfloorTracker


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
    listener._tx_skipped_by_reason = {"no_token_transfer": 2}

    stats = listener.get_stats()

    assert stats["websocket_connected"] is True
    assert stats["last_ws_connected_at"] == "2026-01-01T12:00:00"
    assert stats["last_tx_received_at"] == "2026-01-01T12:03:00"
    assert stats["queue_size"] == 7
    assert stats["queue_max_size"] == 0
    assert stats["queue_fresh_target_size"] == 0
    assert stats["transactions_dropped"] == 0
    assert stats["transaction_skipped_by_reason"] == {"no_token_transfer": 2}
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


def test_solana_listener_drops_oldest_signature_when_queue_is_full():
    listener = object.__new__(SolanaListener)
    listener._max_tx_queue_size = 2
    listener._fresh_tx_queue_target_size = 2
    listener._tx_queue = asyncio.Queue(maxsize=2)
    listener._tx_dropped = 0
    listener._errors = 0

    listener._enqueue_signature("old-a")
    listener._enqueue_signature("old-b")
    listener._enqueue_signature("new-c")

    assert listener._tx_queue.qsize() == 2
    assert listener._tx_dropped == 1
    assert listener._errors == 0
    assert listener._tx_queue.get_nowait() == "old-b"
    assert listener._tx_queue.get_nowait() == "new-c"


def test_solana_listener_records_sns_alert_in_listener_and_tracker_stats():
    listener = object.__new__(SolanaListener)
    listener._sns_alerts_sent = 0
    listener.sns_tracker = SNSTracker()

    listener._record_sns_alert_sent("TokenMint111111111111111111111111111111111111")

    assert listener._sns_alerts_sent == 1
    assert listener.sns_tracker.get_stats()["sns_buys_tracked"] == 1
    assert listener.sns_tracker.get_stats()["alerts_sent"] == 1


def test_strongfloor_does_not_cool_down_before_successful_send(tmp_path, monkeypatch):
    state_file = tmp_path / "strongfloor_state.json"
    monkeypatch.setattr(StrongfloorTracker, "STATE_FILE", str(state_file))
    tracker = StrongfloorTracker()
    old = datetime.utcnow() - timedelta(hours=5)
    tracker._price_history["token"] = [
        (1.00, old),
        (1.08, old + timedelta(minutes=10)),
        (1.01, old + timedelta(minutes=20)),
        (1.12, old + timedelta(minutes=30)),
        (1.02, old + timedelta(minutes=40)),
        (1.15, old + timedelta(minutes=50)),
        (1.03, old + timedelta(minutes=60)),
        (1.10, old + timedelta(minutes=70)),
        (1.04, old + timedelta(minutes=80)),
        (1.16, old + timedelta(minutes=90)),
    ]

    candidate = tracker.analyze_floor(
        token_address="token",
        ticker="FLOOR",
        token_name="Floor Token",
        current_price=1.16,
    )

    assert candidate is not None
    assert tracker.get_stats()["strongfloors_detected"] == 0
    assert state_file.exists() is False
    assert tracker.analyze_floor("token", "FLOOR", "Floor Token", 1.16) is not None

    tracker.mark_alerted(candidate)

    assert tracker.get_stats()["strongfloors_detected"] == 1
    assert state_file.exists() is True
    assert tracker.analyze_floor("token", "FLOOR", "Floor Token", 1.16) is None


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
async def test_solana_listener_sends_streamflow_lock_with_fallback_metadata(monkeypatch):
    listener = object.__new__(SolanaListener)
    listener.streamflow_tracker = _StreamflowTracker()
    listener.token_fetcher = _EmptyTokenFetcher()
    listener.telegram = _Telegram()
    listener._streamflow_alerts_sent = 0

    monkeypatch.setattr("services.solana_listener.settings.telegram_streamflow_topic_id", 1234)

    sent = await listener._maybe_process_streamflow_lock(_streamflow_tx())

    assert sent is True
    assert listener._streamflow_alerts_sent == 1
    assert listener.telegram.messages == [
        ("streamflow:TokenMint111111111111111111111111111111111111:12345", 1234)
    ]


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

class _RotatingRPCManager:
    endpoint_count = 3

    def __init__(self):
        self.urls = ["https://limited-a.example/rpc", "https://limited-b.example/rpc", "https://healthy.example/rpc"]
        self.calls = []
        self.errors = []

    def get_rpc_url(self):
        url = self.urls[len(self.calls)]
        self.calls.append(url)
        return url

    def report_error(self, rpc_url, is_rate_limit=False):
        self.errors.append((rpc_url, is_rate_limit))


class _RPCResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _RotatingHTTPClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, json):
        self.posts.append((url, json["method"]))
        if "limited" in url:
            return _RPCResponse(429, {"error": {"message": "rate limited"}})
        return _RPCResponse(200, {"result": {"meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}})


@pytest.mark.asyncio
async def test_solana_listener_fetch_tries_full_rpc_pool_before_dropping_rate_limited_tx(monkeypatch):
    from services import solana_listener as solana_listener_module

    async def no_sleep(_seconds):
        return None

    listener = object.__new__(SolanaListener)
    listener.rpc_manager = _RotatingRPCManager()
    listener._http_client = _RotatingHTTPClient()
    listener._rpc_semaphore = asyncio.Semaphore(1)
    listener._errors = 0
    processed = []

    async def process(tx_result, signature):
        processed.append((tx_result, signature))

    listener._process_transaction = process
    monkeypatch.setattr(solana_listener_module.asyncio, "sleep", no_sleep)

    await listener._fetch_and_process_tx("sig-123")

    assert processed == [({"meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}, "sig-123")]
    assert listener._errors == 0
    assert listener.rpc_manager.errors == [
        ("https://limited-a.example/rpc", True),
        ("https://limited-b.example/rpc", True),
    ]
    assert listener._http_client.posts == [
        ("https://limited-a.example/rpc", "getTransaction"),
        ("https://limited-b.example/rpc", "getTransaction"),
        ("https://healthy.example/rpc", "getTransaction"),
    ]


def test_strongfloor_stats_explain_missing_floor_pattern(tmp_path, monkeypatch):
    state_file = tmp_path / "strongfloor_state.json"
    monkeypatch.setattr(StrongfloorTracker, "STATE_FILE", str(state_file))
    tracker = StrongfloorTracker()
    tracker.record_price("token", 1.0, "LOW", "Low History")

    candidate = tracker.analyze_floor("token", "LOW", "Low History", 1.0)

    stats = tracker.get_stats()
    assert candidate is None
    assert stats["analysis_attempts"] == 1
    assert stats["rejected_by_reason"] == {"insufficient_history": 1}

class _NoStreamflowTracker:
    def is_streamflow_lock(self, program_ids):
        return False


@pytest.mark.asyncio
async def test_solana_listener_records_no_token_transfer_skip_reason():
    listener = object.__new__(SolanaListener)
    listener._tx_skipped_by_reason = {}
    listener._errors = 0
    listener.streamflow_tracker = _NoStreamflowTracker()

    await listener._process_transaction(
        {
            "meta": {
                "err": None,
                "preBalances": [2_000_000_000],
                "postBalances": [1_900_000_000],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
            "transaction": {
                "message": {
                    "accountKeys": [{"pubkey": "wallet"}],
                    "instructions": [],
                }
            },
        },
        "sig-no-token",
    )

    assert listener._tx_skipped_by_reason == {"no_token_transfer": 1}
    assert listener._errors == 0