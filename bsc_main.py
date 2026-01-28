"""
BSC Bot - Main Entry Point
Run this to start the BSC blockchain listener.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from bsc.bsc_listener import get_bsc_listener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for BSC bot."""
    logger.info("=" * 60)
    logger.info("🟡 BSC BOT - Fresh Wallet & Dormant Tracker")
    logger.info("=" * 60)
    
    listener = get_bsc_listener()
    
    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await listener.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 BSC Bot stopped.")
