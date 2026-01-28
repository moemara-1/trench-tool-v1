import asyncio
from web3 import Web3
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

async def check_bsc():
    rpc_url = os.getenv("BSC_BSC_RPC_URL", "https://bsc-dataseed.binance.org")
    print(f"Checking BSC RPC: {rpc_url}")
    
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if w3.is_connected():
            block_num = w3.eth.block_number
            print(f"Successfully connected! Current block: {block_num}")
            
            # Fetch last 5 blocks
            for i in range(5):
                block = w3.eth.get_block(block_num - i)
                print(f"Block {block_num - i}: {len(block.transactions)} txs")
        else:
            print("Failed to connect to BSC RPC.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_bsc())
