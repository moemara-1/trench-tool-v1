from services.pumpportal_listener import PumpPortalListener


def test_pumpportal_parses_new_token_event_with_creator_and_market_data():
    listener = PumpPortalListener()

    event = listener.parse_event(
        {
            "txType": "create",
            "mint": "PumpMint111111111111111111111111111111111111",
            "symbol": "EARLY",
            "name": "Early Token",
            "traderPublicKey": "Creator1111111111111111111111111111111111",
            "signature": "create-signature",
            "initialBuy": 1.75,
            "marketCapSol": 14.2,
        }
    )

    assert event is not None
    assert event.kind == "new_token"
    assert event.mint == "PumpMint111111111111111111111111111111111111"
    assert event.symbol == "EARLY"
    assert event.creator_wallet == "Creator1111111111111111111111111111111111"
    assert event.initial_buy_sol == 1.75
    assert event.market_cap_sol == 14.2


def test_pumpportal_rejects_trades_and_events_without_mints():
    listener = PumpPortalListener()

    assert listener.parse_event({"txType": "buy", "mint": "not-a-launch"}) is None
    assert listener.parse_event({"txType": "migrate", "symbol": "MISSING"}) is None