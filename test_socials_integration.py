import asyncio
import redis.asyncio as redis
import orjson
from datetime import datetime
from config import settings

async def push_test_token():
    print("Connecting to Redis...")
    client = redis.from_url(settings.redis_url)
    
    # Mock token data with a REAL strong profile to trigger LLM
    payload = {
        "token_address": "TestToken_FixScraper_v3", 
        "twitter_url": "https://twitter.com/solana",
        "token_data": {
            "symbol": "TEST",
            "name": "Test Token (Solana)",
            "mc_string": "$100M",
            "age_string": "1yr",
            "telegram": "https://t.me/solana",
            "twitter": "https://twitter.com/solana",
            "website": "https://solana.com"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    print(f"Pushing test payload for {payload['token_data']['name']}...")
    await client.lpush("trench:socials:queue", orjson.dumps(payload))
    print("Pushed! Check the 'run_socials_local.py' logs now.")

if __name__ == "__main__":
    asyncio.run(push_test_token())
