"""
BSC Blockchain Listener
Monitors BSC for token purchases by fresh and dormant wallets.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any
from collections import defaultdict
from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware
import httpx

from bsc.bsc_config import bsc_settings
from bsc.bsc_api_clients import get_bsc_token_fetcher, get_bscscan_client
from bsc.bsc_wallet_classifier import get_bsc_wallet_classifier
from bsc.bsc_channel_router import get_bsc_channel_router, BSCChannel
from bsc.bsc_tx_tracker import get_bsc_tx_tracker
from bsc.bsc_telegram_bot import get_bsc_telegram_bot

logger = logging.getLogger(__name__)


# Known BSC token addresses
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
USDC_ADDRESS = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
BUSD_ADDRESS = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"

# Stablecoins to exclude from token detection
EXCLUDED_TOKENS = {
    WBNB_ADDRESS.lower(),
    USDT_ADDRESS.lower(),
    USDC_ADDRESS.lower(),
    BUSD_ADDRESS.lower(),
}

# BSC DEXes - Router addresses
BSC_DEX_ROUTERS = {
    # PancakeSwap V2
    "0x10ED43C718714eb63d5aA57B78B54704E256024E": ("pancakeswap_v2", "🥞"),
    # PancakeSwap V3
    "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4": ("pancakeswap_v3", "🥞"),
    # BabySwap
    "0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd": ("babyswap", "👶"),
    # BiSwap
    "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8": ("biswap", "🔄"),
    # ApeSwap
    "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7": ("apeswap", "🦍"),
    # DODO
    "0x8F8Dd7DB1bDA5eD3da8C9daf3bfa471c12d58486": ("dodo", "🐤"),
}

# BSC Launchpads
BSC_LAUNCHPADS = {
    # Four.meme Token Manager
    "0x5c952063c7fc8610FFDB798152D69F0B9550762b": ("four.meme", "🍀"),
    # Meme Rush
    "0x4444b1e4de34df52cf91e30cc7c0336ee03d7c1b": ("meme_rush", "🚀🟡"),
}

# ERC20 Transfer event signature
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Swap event signatures for DEX detection
SWAP_TOPICS = {
    # PancakeSwap V2 Swap
    "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822",
    # Uniswap V2 style Swap
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
}


class BSCListener:
    """Monitors BSC blockchain for token purchases."""
    
    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or bsc_settings.bsc_rpc_url
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # Services
        self.token_fetcher = get_bsc_token_fetcher()
        self.bscscan = get_bscscan_client()
        self.wallet_classifier = get_bsc_wallet_classifier()
        self.channel_router = get_bsc_channel_router()
        self.tx_tracker = get_bsc_tx_tracker()
        self.telegram = get_bsc_telegram_bot()
        
        # State
        self._running = False
        self._processed_txs: Set[str] = set()
        self._seen_tokens: Set[str] = set()
        self._http: Optional[httpx.AsyncClient] = None
        
        # Stats
        self._tx_received = 0
        self._tx_processed = 0
        self._alerts_sent = 0
        self._errors = 0
    
    async def start(self):
        """Start the BSC listener."""
        self._running = True
        self._http = httpx.AsyncClient(timeout=30.0)
        
        logger.info("🚀 Starting BSC listener...")
        
        # Startup notification removed as requested
        # logger.info("BSC Listener started")
        
        # Start block polling
        await self._poll_blocks()
    
    async def stop(self):
        """Stop the listener."""
        self._running = False
        if self._http:
            await self._http.aclose()
        logger.info("BSC listener stopped")
    
    async def _poll_blocks(self):
        """Poll for new blocks and process transactions."""
        last_block = self.w3.eth.block_number
        logger.info(f"📦 Starting from block {last_block}")
        
        while self._running:
            try:
                current_block = self.w3.eth.block_number
                
                if current_block > last_block:
                    logger.info(f"🆕 New BSC blocks detected: {last_block} -> {current_block}")
                    # Process new blocks
                    for block_num in range(last_block + 1, current_block + 1):
                        await self._process_block(block_num)
                        last_block = block_num
                else:
                    if self._tx_received % 100 == 0: # Periodic heartbeat
                         logger.debug(f"ℹ️ BSC Heartbeat: Still at block {last_block}")
                
                # Wait for next poll
                await asyncio.sleep(1)  # BSC has ~3 second blocks
                
            except Exception as e:
                logger.error(f"Block polling error: {e}")
                self._errors += 1
                await asyncio.sleep(5)
    
    async def _process_block(self, block_number: int):
        """Process all transactions in a block."""
        try:
            block = self.w3.eth.get_block(block_number, full_transactions=True)
            
            for tx in block.transactions:
                self._tx_received += 1
                
                # Skip if already processed
                tx_hash = tx.hash.hex()
                if tx_hash in self._processed_txs:
                    continue
                
                self._processed_txs.add(tx_hash)
                logger.debug(f"🔍 Processing BSC TX: {tx_hash[:16]}")
                
                # Limit cache size
                if len(self._processed_txs) > 10000:
                    self._processed_txs = set(list(self._processed_txs)[-5000:])
                
                # Process transaction
                await self._process_transaction(tx, tx_hash)
                
        except Exception as e:
            logger.error(f"Error processing block {block_number}: {e}")
            self._errors += 1
    
    async def _process_transaction(self, tx: Dict, tx_hash: str):
        """Process a single transaction."""
        try:
            # Get transaction receipt for logs
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            if not receipt or receipt.status != 1:
                return  # Failed transaction
            
            # Get buyer (from address)
            buyer = tx.get("from", "")
            if not buyer:
                return
            
            # Calculate BNB spent
            gas_used = receipt.gasUsed
            gas_price = tx.get("gasPrice", 0)
            gas_cost = gas_used * gas_price
            bnb_value = tx.get("value", 0)
            total_bnb_spent = (bnb_value + gas_cost) / 1e18
            
            # Check minimum threshold
            if total_bnb_spent < bsc_settings.min_transaction_bnb:
                return
            
            # Detect token purchase from logs
            token_address = None
            token_amount = 0
            is_usdt_purchase = False
            usdt_amount = 0
            
            for log in receipt.logs:
                # Check for Transfer events
                if len(log.topics) >= 3 and log.topics[0].hex() == TRANSFER_TOPIC:
                    to_address = "0x" + log.topics[2].hex()[-40:]
                    token_addr = log.address.lower()
                    
                    # Check if transfer is TO the buyer
                    if to_address.lower() == buyer.lower():
                        # Skip WBNB and stablecoins as the "purchased" token
                        if token_addr not in EXCLUDED_TOKENS:
                            token_address = log.address
                            # Decode amount from data
                            if log.data:
                                token_amount = int(log.data.hex(), 16)
                        # Check for USDT purchase
                        elif token_addr == USDT_ADDRESS.lower():
                            is_usdt_purchase = True
                            if log.data:
                                usdt_amount = int(log.data.hex(), 16) / 1e18
            
            if not token_address:
                return  # No token purchase detected
            
            self._tx_processed += 1
            logger.info(f"💰 Token buy: {total_bnb_spent:.4f} BNB -> {token_address[:10]}...")
            
            # Detect DEX/launchpad
            to_address = tx.get("to", "")
            launchpad = None
            if to_address in BSC_LAUNCHPADS:
                launchpad, _ = BSC_LAUNCHPADS[to_address]
            
            # Get token data
            token_data = await self.token_fetcher.get_token_data(token_address)
            if not token_data:
                logger.debug(f"Could not fetch token data for {token_address}")
                return
            
            # Classify wallet
            wallet_class = await self.wallet_classifier.classify(buyer)
            
            # Check if first mention
            is_first_mention = token_address not in self._seen_tokens
            
            # Calculate USD value
            amount_usd = usdt_amount if is_usdt_purchase else (total_bnb_spent * 600)  # Rough BNB price
            
            # Route to appropriate channel
            if wallet_class.is_fresh or wallet_class.is_old_fresh:
                await self._handle_freshies_alert(
                    token_data=token_data,
                    wallet_class=wallet_class,
                    amount_bnb=total_bnb_spent,
                    amount_usd=amount_usd,
                    is_first_mention=is_first_mention,
                    is_usdt_purchase=is_usdt_purchase,
                    launchpad=launchpad,
                    tx_hash=tx_hash,
                )
            
            elif wallet_class.is_dormant or wallet_class.is_semi_dormant:
                await self._handle_dormants_alert(
                    token_data=token_data,
                    wallet_class=wallet_class,
                    amount_bnb=total_bnb_spent,
                    amount_usd=amount_usd,
                    is_first_mention=is_first_mention,
                    is_usdt_purchase=is_usdt_purchase,
                    launchpad=launchpad,
                    tx_hash=tx_hash,
                )
            
            # Mark token as seen
            if is_first_mention:
                self._seen_tokens.add(token_address)
            
        except Exception as e:
            logger.error(f"Error processing tx {tx_hash[:16]}: {e}")
            self._errors += 1
    
    async def _handle_freshies_alert(
        self,
        token_data,
        wallet_class,
        amount_bnb: float,
        amount_usd: float,
        is_first_mention: bool,
        is_usdt_purchase: bool,
        launchpad: Optional[str],
        tx_hash: str,
    ):
        """Handle freshies alert routing."""
        
        # Classify for channel routing
        classification = self.channel_router.classify_freshies(
            wallet=wallet_class,
            amount_bnb=amount_bnb,
            amount_usd=amount_usd,
            market_cap=token_data.market_cap,
            is_first_mention=is_first_mention,
            is_usdt_purchase=is_usdt_purchase,
            launchpad=launchpad,
        )
        
        if not classification.is_valid_alert:
            return
        
        # Record in tracker
        stats = self.tx_tracker.record_fresh_buy(
            token_address=token_data.address,
            wallet=wallet_class.wallet_address,
            tx_hash=tx_hash,
        )
        
        # Get counter
        counter = self.tx_tracker.increment_channel_counter(
            token_address=token_data.address,
            channel=classification.channel.value,
        )
        
        # Format alert
        message = self.telegram.format_freshies_alert(
            token=token_data,
            classification=classification,
            stats=stats,
            wallet_classification=wallet_class,
            amount_bnb=amount_bnb,
            amount_usd=amount_usd,
            counter=counter,
        )
        
        # Send alert
        await self.telegram.send_alert(message, topic_id=classification.topic_id)
        self._alerts_sent += 1
        logger.info(f"✅ Freshies alert sent: ${token_data.symbol}")
    
    async def _handle_dormants_alert(
        self,
        token_data,
        wallet_class,
        amount_bnb: float,
        amount_usd: float,
        is_first_mention: bool,
        is_usdt_purchase: bool,
        launchpad: Optional[str],
        tx_hash: str,
    ):
        """Handle dormants/semi-dormants alert routing."""
        
        # Classify for channel routing
        classification = self.channel_router.classify_dormants(
            wallet=wallet_class,
            amount_bnb=amount_bnb,
            amount_usd=amount_usd,
            market_cap=token_data.market_cap,
            is_first_mention=is_first_mention,
            is_usdt_purchase=is_usdt_purchase,
            launchpad=launchpad,
        )
        
        if not classification.is_valid_alert:
            return
        
        # Record in tracker
        self.tx_tracker.record_dormant_buy(
            token_address=token_data.address,
            wallet=wallet_class.wallet_address,
            tx_hash=tx_hash,
        )
        
        # Get counter
        counter = self.tx_tracker.increment_channel_counter(
            token_address=token_data.address,
            channel=classification.channel.value,
        )
        
        # Format alert
        message = self.telegram.format_dormants_alert(
            token=token_data,
            classification=classification,
            wallet_classification=wallet_class,
            amount_bnb=amount_bnb,
            amount_usd=amount_usd,
            counter=counter,
        )
        
        # Send alert
        await self.telegram.send_alert(message, topic_id=classification.topic_id)
        self._alerts_sent += 1
        logger.info(f"✅ Dormants alert sent: ${token_data.symbol}")


# Singleton
_listener: Optional[BSCListener] = None


def get_bsc_listener() -> BSCListener:
    """Get singleton BSC listener."""
    global _listener
    if _listener is None:
        _listener = BSCListener()
    return _listener
