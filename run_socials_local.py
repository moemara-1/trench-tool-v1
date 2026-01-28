"""
Trench Tool V1 - Local Socials Runner
Runs the socials checker locally with FrontrunPro support.

This script monitors tokens from the Redis queue (populated by Docker bot)
and checks their socials using Playwright with the FrontrunPro Chrome extension.

Usage:
    python run_socials_local.py
"""

import asyncio
import logging
import sys
import json
import redis.asyncio as redis
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from services.smart_follower_scraper import get_smart_follower_scraper
from services.socials_checker import get_socials_checker
from alerts.telegram_bot import get_telegram_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("socials_runner.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# Redis queue key for socials requests
SOCIALS_QUEUE_KEY = "trench:socials:queue"

async def process_queue():
    """Poll Redis queue and process tokens."""
    logger.info("🔄 Connecting to Redis...")
    redis_client = redis.from_url(settings.redis_url)
    
    logger.info("� Socials Runner Started! Waiting for tokens...")
    
    scraper = get_smart_follower_scraper()
    checker = get_socials_checker()
    telegram = get_telegram_bot()
    
    # Initialize browser once
    await scraper.initialize()
    if scraper._extension_loaded:
        logger.info("✅ FrontrunPro extension loaded")
    else:
        logger.warning("⚠️ Running in estimation mode (no extension)")
    
    while True:
        try:
            # Blocking pop from queue (wait 5s timeout to allow clean exit check)
            item = await redis_client.brpop(SOCIALS_QUEUE_KEY, timeout=5)
            
            if not item:
                continue
                
            # Item is tuple (key, value)
            _, data_json = item
            data = json.loads(data_json)
            
            token_address = data.get("token_address")
            twitter_url = data.get("twitter_url")
            token_data = data.get("token_data", {})
            
            # Filter by age (max 1 week = 168 hours)
            age_hours = token_data.get("age_hours", 0)
            
            # Fallback for old queue items: Parse string "355d", "10h" etc.
            if age_hours == 0 and "age_string" in token_data:
                age_str = token_data.get("age_string", "").lower()
                try:
                    if "d" in age_str:
                        days = int(float(age_str.replace("d", "").strip()))
                        age_hours = days * 24
                    elif "h" in age_str:
                        age_hours = int(float(age_str.replace("h", "").strip()))
                    # Minutes ("m") implies fresh, so ignore
                except:
                    pass
            
            if age_hours > 168:
                logger.info(f"⏳ Skipping {token_data.get('symbol', '???')}: Too old ({age_hours}h > 168h)")
                continue
            
            logger.info(f"📱 Processing {token_data.get('symbol', '???')}: {token_address[:8]}... (Age: {age_hours}h)")
            
            # 1. Basic check
            # Convert dict back to object structure expected by checker (or pass dict if supported)
            # The checker expects a dict for token_data
            profile = await checker.check_socials(token_address, token_data)
            
            if not profile:
                logger.info(f"   No profile created for {token_address}")
                continue
                
            if not checker.is_strong_socials(profile):
                logger.info(f"   Weak socials (score: {profile.social_score})")
                continue
                
            # 2. Enhanced analysis (uses the already-initialized scraper internally)
            # Since we are in the same process, get_smart_follower_scraper() returns the singleton
            # that we initialized above.
            
            logger.info(f"   🧠 Analyzing enhanced stats...")
            profile = await checker.analyze_enhanced(profile)
            
            # 3. Alert if good enough
            if checker.is_enhanced_socials(profile):
                ticker = token_data.get("symbol", "???")
                name = token_data.get("name", "Unknown")
                mc = token_data.get("mc_string", "?")
                age = token_data.get("age_string", "?")
                
                message = await checker.format_socials_alert(
                    ticker=ticker,
                    token_name=name,
                    contract_address=token_address,
                    profile=profile,
                    market_cap_str=mc,
                    coin_age_str=age
                )
                
                topic_id = settings.telegram_socials_topic_id
                if topic_id > 0:
                    await telegram.send_alert(message, topic_id=topic_id)
                    checker.mark_alerted(token_address)
                    logger.info(f"   ✅ ALERT SENT! (Score: {profile.enhanced_score})")
                else:
                    logger.warning("   ⚠️ Alert skipped: TELEGRAM_SOCIALS_TOPIC_ID not set")
            else:
                logger.info(f"   Score too low: {profile.enhanced_score}/100 (need >70)")
                
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            await asyncio.sleep(1)

async def main():
    try:
        await process_queue()
    except KeyboardInterrupt:
        logger.info("Stopping...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
