
import asyncio
from config import settings
from alerts.telegram_bot import get_telegram_bot

async def test_msg():
    bot = get_telegram_bot()
    print(f"Token: {bot.token[:5]}...")
    print(f"Chat ID: {bot.chat_id}")
    print(f"Topic ID from settings: {settings.telegram_feedback_topic_id}")
    
    # Target topic from settings (should be 0/None based on .env)
    topic_id = settings.telegram_feedback_topic_id if settings.telegram_feedback_topic_id > 0 else None
    
    msg = """🟢 <b>TRUNCH TOOL V1 - SYSTEMS ONLINE (Debug Test)</b>

<b>Solana Monitors:</b>
✅ Fresh Wallets (Age < 7d)
✅ Dormant Wallets (> 30d)
✅ Bundle Detection
✅ Pattern Recognition
✅ Smart Socials (FrontrunPro + Gemini)
✅ Strong Launches & Floors
✅ Late Migrations & Dev Tracking

<b>BSC Monitors:</b>
✅ Fresh & Dormant Tracking
✅ DEX Monitoring (Pancake, etc.)

<b>Infrastructure:</b>
📡 Helius RPC: Connected
🤖 Gemini AI: Active
🔌 FrontrunPro Extension: Loaded"""
    
    print(f"Token: {bot.token[:5]}...")
    print(f"Chat ID: {bot.chat_id}")
    print(f"Configured Topic ID: {settings.telegram_feedback_topic_id}")
    print(f"Targeting Topic: {topic_id}")
    
    try:
        await bot.send_alert(msg, topic_id=topic_id)
        print("Message sent successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_msg())
