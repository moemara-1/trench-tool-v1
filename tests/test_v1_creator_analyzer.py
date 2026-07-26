from datetime import datetime

import pytest

from services.creator_analyzer import CreatorProfile, GoodCreatorAnalyzer


def test_good_creator_stats_explain_rejected_profiles():
    analyzer = GoodCreatorAnalyzer()
    analyzer._profiles["weak"] = CreatorProfile(
        wallet_address="weak",
        tokens_created=[],
        successful_tokens=[],
        total_wallet_value_usd=10,
        first_seen=datetime.utcnow(),
        is_good_creator=False,
        score=5,
    )
    analyzer._profiles["strong"] = CreatorProfile(
        wallet_address="strong",
        tokens_created=[],
        successful_tokens=["winner"],
        total_wallet_value_usd=10_000,
        first_seen=datetime.utcnow(),
        is_good_creator=True,
        score=80,
    )

    stats = analyzer.get_stats()

    assert stats["good_creators"] == 1
    assert stats["rejected_creators"] == 1
    assert stats["best_creator_score"] == 80

def test_good_creator_requires_verified_success_history():
    analyzer = GoodCreatorAnalyzer()

    assert analyzer.check_is_good_creator_from_values(
        wallet_value_sol=25,
        wallet_value_usd=25_000,
        successful_count=0,
    ) is False
    assert analyzer.check_is_good_creator_from_values(
        wallet_value_sol=0,
        wallet_value_usd=0,
        successful_count=1,
    ) is True


def test_creator_history_uses_only_verified_prior_creator_mints_above_threshold():
    analyzer = GoodCreatorAnalyzer()
    wallet = "Creator1111111111111111111111111111111111111"
    current_mint = "Current1111111111111111111111111111111111111"
    low_mint = "Low111111111111111111111111111111111111111"
    winner_mint = "Winner1111111111111111111111111111111111111"

    tokens_created, successful_tokens = analyzer._summarize_creator_history(
        [
            {"mint": current_mint, "creator": wallet, "ath_market_cap": 2_000_000},
            {"mint": low_mint, "creator": wallet, "ath_market_cap": 200_000},
            {"mint": winner_mint, "creator": wallet, "ath_market_cap": 750_000},
            {"mint": "Foreign11111111111111111111111111111111111", "creator": "Other111111111111111111111111111111111111", "ath_market_cap": 2_000_000},
        ],
        wallet_address=wallet,
        current_token_address=current_mint,
    )

    assert tokens_created == [low_mint, winner_mint]
    assert successful_tokens == [winner_mint]

@pytest.mark.asyncio
async def test_creator_analysis_avoids_rpc_when_history_has_no_verified_success(monkeypatch):
    from services import creator_analyzer as creator_analyzer_module

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    class Manager:
        calls = 0

        def get_rpc_url(self):
            self.calls += 1
            raise AssertionError("unproven creators must not consume RPC quota")

    analyzer = GoodCreatorAnalyzer()
    manager = Manager()

    async def history(_client, wallet_address):
        return [
            {
                "mint": "PriorLowMint",
                "creator": wallet_address,
                "ath_market_cap": 200_000,
            }
        ]

    monkeypatch.setattr(creator_analyzer_module.httpx, "AsyncClient", lambda timeout: Client())
    monkeypatch.setattr(creator_analyzer_module, "get_rpc_manager", lambda: manager)
    monkeypatch.setattr(analyzer, "_fetch_creator_history", history)

    profile = await analyzer.analyze_creator("CreatorWallet", current_token_address="CurrentMint")

    assert profile is not None
    assert profile.successful_tokens == []
    assert profile.total_wallet_value_usd == 0
    assert manager.calls == 0


@pytest.mark.asyncio
async def test_creator_history_fetch_uses_pumpfun_v3_creator_filter():
    class Response:
        status_code = 200

        def json(self):
            return [{"mint": "PriorMint", "creator": "CreatorWallet"}]

    class Client:
        def __init__(self):
            self.calls = []

        async def get(self, url, params, timeout):
            self.calls.append((url, params, timeout))
            return Response()

    analyzer = GoodCreatorAnalyzer()
    client = Client()

    history = await analyzer._fetch_creator_history(client, "CreatorWallet")

    assert history == [{"mint": "PriorMint", "creator": "CreatorWallet"}]
    assert client.calls == [
        (
            "https://frontend-api-v3.pump.fun/coins",
            {
                "limit": 50,
                "offset": 0,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "false",
                "creator": "CreatorWallet",
            },
            5.0,
        )
    ]