import asyncio
import logging
import os
from collections import namedtuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import sys
sys.stdout.reconfigure(encoding='utf-8')

async def run_tests():
    print("🚀 Starting All-Channel Verification Test...")
    
    from alerts.telegram_bot import get_telegram_bot
    from services.solana_listener import get_solana_listener
    from config import settings
    
    telegram = get_telegram_bot()
    listener = get_solana_listener()
    
    # Define all topics to test
    topics = [
        ("SOL Freshies", settings.telegram_freshies_topic_id, "🟠"),
        ("Freshies Wizard", settings.telegram_wizard_topic_id, "🧙‍♂️"),
        ("SOL Dormant", settings.telegram_dormants_topic_id, "⏳"),
        ("SOL Bundles", settings.telegram_bundles_topic_id, "📦"),
        ("Vanish Buys", settings.telegram_vanish_topic_id, "👻"),
        ("Streamflow", settings.telegram_streamflow_topic_id, "🔒"),
        ("Dev Held", settings.telegram_dev_held_topic_id, "👨‍💻"),
        ("Good Creator", settings.telegram_good_creator_topic_id, "🎨"),
        ("Socials", settings.telegram_socials_topic_id, "📱"),
        ("Strong Launch", settings.telegram_strong_launch_topic_id, "🚀"),
        ("Strong Floor", settings.telegram_strongfloor_topic_id, "🧱"),
        ("Late Migration", settings.telegram_late_migration_topic_id, "🐢"),
        
        # BSC (Not in Settings class yet, read from env)
        ("BSC Freshies", int(os.getenv("BSC_TELEGRAM_BSC_FRESHIES_TOPIC_ID", "1091")), "🥞"),
        ("BSC Dormants", int(os.getenv("BSC_TELEGRAM_BSC_DORMANTS_TOPIC_ID", "1101")), "💤"),
    ]
    
    print(f"Testing {len(topics)} topics...")
    
    for name, topic_id, emoji in topics:
        if not topic_id or topic_id == 0:
            print(f"⏭️ Skipping {name} (ID 0 or None)")
            continue
            
        try:
            msg = f"{emoji} **TEST ALERT**\n\nChecking channel: **{name}**\nID: `{topic_id}`\nStatus: ✅ Operational"
            await telegram.send_alert(msg, topic_id=topic_id)
            print(f"✅ Sent to {name} (ID: {topic_id})")
            await asyncio.sleep(0.5) # Avoid rate limits
        except Exception as e:
            print(f"❌ Failed to reach {name}: {e}")

    # Test Local Runner Queue Push (Socials)
    print("\n📩 Pushing item to Socials Queue (for Local Runner check)...")
    token_obj = namedtuple('TokenData', ['address', 'symbol', 'name', 'mc_string', 'age_string', 'twitter', 'telegram', 'website', 'price_usd'])(
        "So11111111111111111111111111111111111111112",
        "TEST-QUEUE", "Test Queue Item", "$1M", "1d", 
        "https://x.com/solana", "https://t.me/solana", "https://solana.com", 150.0
    )
    
    try:
        await listener._send_to_socials_queue(token_obj, "https://x.com/solana")
        print("✅ Pushed to Redis queue (Local runner should pick this up)")
    except Exception as e:
        print(f"❌ Failed to push to queue: {e}")

if __name__ == "__main__":
    asyncio.run(run_tests())
