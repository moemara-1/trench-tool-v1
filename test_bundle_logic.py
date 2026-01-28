import asyncio
from datetime import datetime
from services.bundle_detector import get_bundle_detector
from models import TradeAction

async def test_bundle_logic():
    detector = get_bundle_detector()
    token = "TEST_TOKEN_123"
    
    print("Testing Bundle Logic...")
    
    # 1. Add "dust" transactions (should not trigger)
    print("Adding dust transactions (0.1 SOL)...")
    for i in range(5):
        detector.add_transaction(token, f"wallet_{i}", 0.1, TradeAction.BUY, block_number=100)
    
    bundle = detector._detect_bundle(token)
    if bundle:
        print(f"❌ Error: Dust bundle detected unexpectedly: {bundle}")
    else:
        print("✅ Correct: No dust bundle detected.")
        
    # 2. Add valid transactions in different blocks (should not trigger same-block bundle)
    print("Adding valid transactions in different blocks...")
    for i in range(3):
        detector.add_transaction(token, f"wallet_v_{i}", 0.5, TradeAction.BUY, block_number=100 + i)
        
    bundle = detector._detect_bundle(token)
    if bundle:
        print(f"❌ Error: Cross-block bundle detected unexpectedly: {bundle}")
    else:
        print("✅ Correct: No cross-block bundle detected.")
        
    # 3. Add valid transactions in same block (SHOULD trigger)
    print("Adding valid transactions in SAME block (0.5 SOL each)...")
    for i in range(3):
        detector.add_transaction(token, f"wallet_s_{i}", 0.5, TradeAction.BUY, block_number=200)
        
    bundle = detector._detect_bundle(token)
    if bundle:
        print(f"✅ Success: Bundle detected in block 200 with {bundle.wallet_count} wallets.")
        print(f"   Bundle ID: {bundle.bundle_id}")
        print(f"   Opening Bundle: {bundle.is_opening_bundle}")
    else:
        print("❌ Error: Same-block bundle NOT detected.")

if __name__ == "__main__":
    asyncio.run(test_bundle_logic())
