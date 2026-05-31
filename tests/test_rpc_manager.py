from services.rpc_manager import HeliusRPCManager


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
