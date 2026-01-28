
import asyncio
import logging
import sys
from datetime import datetime

# Setup path
import os
sys.path.append(os.getcwd())

from database import init_database, close_database, get_db_session
from services.freshies_tracker import get_freshies_tracker
from models import Token, Wallet, WalletType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_integration():
    await init_database()
    
    tracker = get_freshies_tracker()
    
    token_addr = f"TEST_TOKEN_{int(datetime.utcnow().timestamp())}"
    wallet_addr = f"TEST_WALLET_{int(datetime.utcnow().timestamp())}"
    
    logger.info(f"Testing with Token: {token_addr}")
    
    async with get_db_session() as session:
        # 1. Create Token
        token = await tracker.get_or_create_token(
            session, 
            contract_address=token_addr,
            name="Integration Test",
            symbol="TEST",
            launchpad="pump.fun"
        )
        
        # 2. Create Wallet
        wallet = Wallet(
            address=wallet_addr,
            wallet_type=WalletType.FRESH,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            transaction_count=5
        )
        session.add(wallet)
        await session.flush()
        
        # 3. Process Purchase (Silent)
        freshie = await tracker.process_token_purchase(
            session=session,
            wallet=wallet,
            token=token,
            tx_signature="sig_test_123",
            amount_sol=1.5,
            suppress_alert=True
        )
        
        if freshie:
            logger.info("✅ Freshie record created successfully")
        else:
            logger.error("❌ Failed to create Freshie record")
            
        # 4. Check Metrics
        metrics = await tracker.get_bbb_metrics(session, token_addr)
        logger.info(f"Metrics: {metrics}")
        
        assert metrics["fresh_buy_count"] == 1
        logger.info("✅ Fresh buy count verified (1)")
        
        # 5. Process Second Purchase (Same wallet)
        await tracker.process_token_purchase(
            session=session,
            wallet=wallet,
            token=token,
            tx_signature="sig_test_456",
            amount_sol=2.0,
            suppress_alert=True
        )
        
        metrics = await tracker.get_bbb_metrics(session, token_addr)
        logger.info(f"Metrics after 2nd buy: {metrics}")
        
        # Note: Tracker counts *events*, not unique wallets, currently. 
        # freshies_tracker.py: select(func.count(Freshie.id))...
        assert metrics["fresh_buy_count"] == 2
        logger.info("✅ Fresh buy count verified (2)")

    await close_database()

if __name__ == "__main__":
    asyncio.run(test_integration())
