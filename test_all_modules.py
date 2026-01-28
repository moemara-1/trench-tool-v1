
import asyncio
import logging
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Setup path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TEST_SUITE")

# Import trackers
from services.late_migration_tracker import get_late_migration_tracker
from services.streamflow_tracker import get_streamflow_tracker
from services.dev_held_tracker import get_dev_held_tracker
from services.creator_analyzer import get_good_creator_analyzer
from services.socials_checker import get_socials_checker
from services.strong_launch_tracker import get_strong_launch_tracker
from services.strongfloor_tracker import get_strongfloor_tracker
from services.vanish_protocol import get_vanish_tracker

async def test_late_migration():
    logger.info("🧪 Testing Late Migration Tracker...")
    tracker = get_late_migration_tracker()
    
    # Mock date
    now = datetime.utcnow()
    # Mock token launch time (25 hours ago)
    
    # Since check_late_bonding uses RPC calls, we'll test the format_alert
    msg = await tracker.format_late_migration_alert(
        ticker="TEST",
        token_name="Test Coin",
        contract_address="So1...",
        delay_hours=25.0,
        market_cap_str="$100k"
    )
    assert "🕐" in msg
    assert "25.0h" in msg
    logger.info("✅ Late Migration Tracker passed")

async def test_streamflow():
    logger.info("🧪 Testing Streamflow Tracker...")
    tracker = get_streamflow_tracker()
    
    # Test specific program ID
    assert tracker.is_streamflow_lock(["mnkw8pprcwh87xrvsdw484q9p52qq9470"]) # Actual streamflow pid check
    
    msg = await tracker.format_streamflow_alert(
        ticker="LOCK",
        token_name="Locked Coin",
        contract_address="So1...",
        lock_amount=1000.0,
        market_cap_str="$50k",
        coin_age_str="1h"
    )
    assert "🔒" in msg
    assert "1,000" in msg
    logger.info("✅ Streamflow Tracker passed")

async def test_dev_held():
    logger.info("🧪 Testing Dev Held Tracker...")
    tracker = get_dev_held_tracker()
    
    tracker.record_dev_wallet("So1...", "DevWallet123", 1000.0)
    stats = tracker.get_stats()
    assert stats["devs_holding"] >= 1
    
    # Simulate update
    tracker.update_holding("So1...", 1000.0) # Still holding
    should_alert = tracker.check_should_alert("So1...")
    # Might limit based on time, but basic logic works
    
    msg = await tracker.format_dev_held_alert(
        ticker="DEV",
        token_name="Dev Coin",
        contract_address="So1...",
        holding_hours=1.0,
        supply_pct=10.0,
        market_cap_str="$20k"
    )
    assert "💎" in msg
    assert "10%" in msg
    logger.info("✅ Dev Held Tracker passed")

async def test_creator_analyzer():
    logger.info("🧪 Testing Creator Analyzer...")
    analyzer = get_good_creator_analyzer()
    
    # Mock profile
    mock_profile = MagicMock()
    mock_profile.successful_tokens = ["Token1", "Token2"]
    mock_profile.total_wallet_value_usd = 50000.0
    
    msg = await analyzer.format_good_creator_alert(
        ticker="CREATOR",
        token_name="Creator Coin",
        contract_address="So1...",
        creator_wallet="Wallet123",
        successful_tokens=2,
        wallet_value_str="$50,000",
        market_cap_str="$10k"
    )
    assert "👑" in msg
    assert "2 Successful" in msg
    logger.info("✅ Creator Analyzer passed")

async def test_vanish_protocol():
    logger.info("🧪 Testing Vanish Protocol...")
    tracker = get_vanish_tracker()
    
    # Test program detection (Assuming Vanish PID is known and checked)
    # Checking logic instead
    
    msg = await tracker.format_vanish_alert(
        ticker="VANISH",
        token_name="Vanish Coin",
        contract_address="So1...",
        amount_sol=2.0,
        market_cap_str="$500k",
        coin_age_str="2h",
        vanish_type=MagicMock(value="vanish_deployer_buy"),
        count=1,
        launchpad_emoji="",
        dex_emoji="",
        is_first_mention=True,
        is_whale=False
    )
    assert "🐍" in msg
    logger.info("✅ Vanish Protocol passed")

async def test_strongfloor():
    logger.info("🧪 Testing Strongfloor...")
    tracker = get_strongfloor_tracker()
    
    tracker.record_price("So1...", 1.0, "FLOOR", "Floor Coin")
    tracker.record_price("So1...", 1.0, "FLOOR", "Floor Coin") # Stable price
    
    # Should detect floor after multiple stable updates
    # Just checking record_price doesn't crash
    
    start_token = MagicMock(ticker="FLOOR", price_std_dev=0.01, support_level=1.0)
    start_token.floor_price = 1.0 # Need to set this explicitly for comparison
    
    msg = await tracker.format_strongfloor_alert(
        token=start_token,
        market_cap_str="$1M"
    )
    assert "🧱" in msg
    logger.info("✅ Strongfloor passed")

async def run_all():
    logger.info("🚀 Starting Comprehensive Module Test")
    
    tests = [
        test_late_migration,
        test_streamflow,
        test_dev_held,
        test_creator_analyzer,
        test_vanish_protocol,
        test_strongfloor
    ]
    
    for test in tests:
        try:
            await test()
        except Exception as e:
            logger.error(f"❌ {test.__name__} Failed: {e}", exc_info=True)
            
    logger.info("🏁 Test Suite Completed")


if __name__ == "__main__":
    asyncio.run(run_all())
