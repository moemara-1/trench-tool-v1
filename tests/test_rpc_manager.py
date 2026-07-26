import pytest
from services.rpc_manager import HeliusRPCManager, init_rpc_manager


def test_rpc_manager_rotates_websocket_after_rate_limit():
    manager = HeliusRPCManager(["key-a", "key-b"])

    first_url = manager.get_ws_url()
    manager.report_error(first_url, is_rate_limit=True)
    second_url = manager.get_ws_url()

    assert "key-a" in first_url
    assert "key-b" in second_url


def test_rpc_manager_reports_rate_limits_for_websocket_urls():
    manager = HeliusRPCManager(["key-a"])
    ws_url = manager.get_ws_url()

    manager.report_error(ws_url, is_rate_limit=True)
    stats = manager.get_stats()

    assert stats["total_errors"] == 1
    assert stats["endpoints"][0]["last_429"] is not None


def test_rpc_manager_reports_pool_cooldown_when_all_keys_are_limited():
    manager = HeliusRPCManager(["key-a", "key-b"])

    first_url = manager.get_ws_url()
    second_url = manager.get_ws_url()
    manager.report_error(first_url, is_rate_limit=True)
    manager.report_error(second_url, is_rate_limit=True)

    assert manager.seconds_until_available() > 0


def test_rpc_manager_uses_generic_fallback_when_helius_keys_are_limited():
    manager = HeliusRPCManager(
        ["key-a"],
        fallback_rpc_url="https://solana-mainnet.g.alchemy.com/v2/test-key",
        fallback_ws_url="wss://solana-mainnet.g.alchemy.com/v2/test-key",
    )

    helius_url = manager.get_rpc_url()
    manager.report_error(helius_url, is_rate_limit=True)
    fallback_url = manager.get_rpc_url()

    assert "mainnet.helius-rpc.com" in helius_url
    assert fallback_url == "https://solana-mainnet.g.alchemy.com/v2/test-key"




def test_init_rpc_manager_can_prefer_alchemy_fallback_for_http_requests():
    fallback_rpc_url = "https://solana-mainnet.g.alchemy.com/v2/test-key"
    manager = init_rpc_manager(
        ["key-a"],
        fallback_rpc_url=fallback_rpc_url,
        fallback_ws_url="wss://solana-mainnet.g.alchemy.com/v2/test-key",
        prefer_fallback_rpc=True,
    )

    assert manager.get_rpc_url() == fallback_rpc_url
def test_init_rpc_manager_can_use_alchemy_fallback_for_log_subscriptions():
    fallback_rpc_url = "https://solana-mainnet.g.alchemy.com/v2/test-key"
    fallback_ws_url = "wss://solana-mainnet.g.alchemy.com/v2/test-key"
    manager = init_rpc_manager(
        ["key-a"],
        fallback_rpc_url=fallback_rpc_url,
        fallback_ws_url=fallback_ws_url,
        fallback_ws_supports_log_subscriptions=True,
    )

    helius_url = manager.get_ws_url()
    manager.report_error(helius_url, is_rate_limit=True)

    assert manager.get_ws_url() == fallback_ws_url
def test_rpc_manager_skips_http_only_fallback_for_log_subscriptions():
    manager = HeliusRPCManager(
        ["key-a"],
        fallback_rpc_url="https://solana-mainnet.g.alchemy.com/v2/test-key",
        fallback_ws_url="wss://solana-mainnet.g.alchemy.com/v2/test-key",
    )

    first_url = manager.get_ws_url()
    second_url = manager.get_ws_url()

    assert "mainnet.helius-rpc.com" in first_url
    assert "mainnet.helius-rpc.com" in second_url
    assert manager.get_all_ws_urls() == [first_url]


def test_rpc_manager_does_not_sleep_when_all_log_websockets_are_cooling(monkeypatch):
    manager = HeliusRPCManager(["key-a", "key-b"])
    first_url = manager.get_ws_url()
    second_url = manager.get_ws_url()
    manager.report_error(first_url, is_rate_limit=True)
    manager.report_error(second_url, is_rate_limit=True)

    def fail_if_called(_seconds):
        raise AssertionError("get_ws_url must not block the event loop")

    monkeypatch.setattr("services.rpc_manager.time.sleep", fail_if_called)

    assert manager.get_ws_url() in {first_url, second_url}



def test_rpc_manager_never_blocks_when_all_rpc_endpoints_are_cooling(monkeypatch):
    manager = HeliusRPCManager(["key-a", "key-b"])
    first_url = manager.get_rpc_url()
    second_url = manager.get_rpc_url()
    manager.report_error(first_url, is_rate_limit=True)
    manager.report_error(second_url, is_rate_limit=True)
    manager._last_request_time = 0

    def fail_if_called(_seconds):
        raise AssertionError("get_rpc_url must not block the event loop")

    monkeypatch.setattr("services.rpc_manager.time.sleep", fail_if_called)

    with pytest.raises(RuntimeError, match="all RPC endpoints are cooling"):
        manager.get_rpc_url()
def test_rpc_manager_escalates_cooldown_after_consecutive_rate_limits():
    manager = HeliusRPCManager(["key-a"])
    url = manager.get_rpc_url()

    manager.report_error(url, is_rate_limit=True)
    first_wait = manager.seconds_until_available()
    manager.report_error(url, is_rate_limit=True)
    second_wait = manager.seconds_until_available()

    assert second_wait > first_wait