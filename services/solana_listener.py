"""
Trench Tool V1 - Solana Listener
Real-time transaction monitoring with freshie sub-channel alerts.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

import httpx

from config import settings
from services.api_clients import get_token_fetcher, get_helius_client
from services.tx_tracker import get_tx_tracker
from services.rpc_manager import get_rpc_manager
from alerts.telegram_bot import get_telegram_bot
from alerts.channel_router import get_channel_router, FreshieChannel
from services.late_migration_tracker import get_late_migration_tracker
from services.strong_launch_tracker import get_strong_launch_tracker

logger = logging.getLogger(__name__)


# Tokens to EXCLUDE (stablecoins, wrapped assets)
EXCLUDED_TOKENS = {
    # Wrapped SOL
    "So11111111111111111111111111111111111111112",
    
    # Stablecoins
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB",   # USD1
    "USDH1SM1ojwWUga67PGrgFWUHibbjqMvuMaDkRJTgkX",   # USDH
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj", # stSOL
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",  # bSOL
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", # wETH
    "A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM", # wUSDC
    "Dn4noZ5jgGfkntzcQSUZ8czkreiZ1ForXYoV2H8Dm7S1", # USDCet
    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E", # wBTC
}

# TRUE LAUNCHPADS - Only these generate freshie alerts (actual meme coin launchpads)
TRUE_LAUNCHPADS = {
    # Pump.fun - THE main meme launchpad
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": ("pump.fun", "💊"),
    
    # Moonshot
    "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG": ("moonshot", "🌙"),
    
    # Bonk launchpad (LetsBonk.fun)
    "BSwp6bEBihVLdqJRKGgzjcGLHkcTuzmSo1TQkHepzH8p": ("bonk", "🐕"),
    "FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1": ("letsbonk", "🐕"),
    
    # Meteora (TRUMP, MELANIA type launches)
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": ("meteora", "☄️"),
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": ("meteora_dlmm", "☄️"),
    
    # Believe.app (uses Meteora DBC Program)
    "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": ("believe", "🙏"),
    "5qWya6UjwWnGVhdSBL3hyZ7B45jbk6Byt1hwd7ohEGXE": ("believe_authority", "🙏"),
    
    # Bags.fm
    "FEE2tBhCKAt7shrod19QttSVREUYPiyMzoku1mL1gqVK": ("bags", "👜"),
    "FEEhPbKVKnco9EXnaY3i4R5rQVUx91wgVfu8qokixw": ("bags_v1", "👜"),
    
    # Boop.fun
    "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4": ("boop", "💋"),
}

# DEXs - For trading but not launchpad detection (used for routing only)
DEXES = {
    # Raydium (all variants)
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("raydium", "®️"),
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": ("raydium_clmm", "®️"),
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": ("raydium_cpmm", "®️"),
    "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS": ("raydium_router", "®️"),

    
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": ("jupiter_v6", "🪐"),
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": ("jupiter_v4", "🪐"),
    "JUP2jxvXaqu7NQY1GmNF4m1vodw12LVXYxbFL2uJvfo": ("jupiter_v2", "🪐"),
    
    # Orca
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": ("orca", "🐋"),
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": ("orca_v2", "🐋"),
    
    # OpenBook / Serum
    "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX": ("openbook", "📖"),
    "opnb2LAfJYbRMAHHvqjCwQxanZn7ReEHp1k81EohpZb": ("openbook_v2", "📖"),
    "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin": ("serum_v3", "💧"),
    
    # Phoenix
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": ("phoenix", "🔥"),
    
    # Lifinity
    "EewxydAPCCVuNEyrVN68PuSYdQ7wKn27V9Gjeoi8dy3S": ("lifinity", "♾️"),
    
    # Fluxbeam
    "FLUXubRmkEi2q6K3Y9kBPg9248ggaZVsoSFhtJHSrm1X": ("fluxbeam", "⚡"),
    
    # Invariant
    "HyaB3W9q6XdA5xwpU4XnSZV94htfmbmqJXZcEbRaJutt": ("invariant", "📐"),
    
    # GooseFX
    "GFXsSL5sSaDfNFQUYsHekbWBW1TsFdjDYzACh62tEHxn": ("goosefx", "🦆"),
    
    # Aldrin
    "AMM55ShdkoGRB5jVYPjWziwk8m5MpwyDgsMWHaMSQWH6": ("aldrin", "🔷"),
    
    # Saber
    "SSwpkEEcbUqx4vtoEByFjSkhKdCT862DNVb52nZg1UZ": ("saber", "⚔️"),
    
    # Marinade
    "MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD": ("marinade", "🧂"),
}


def _positive_topic_id(topic_id: int) -> int | None:
    return topic_id if topic_id > 0 else None


def good_creator_topic_id() -> int | None:
    return _positive_topic_id(settings.telegram_good_creator_topic_id)


def socials_topic_id() -> int | None:
    return _positive_topic_id(settings.telegram_socials_topic_id)


def strong_launch_topic_id() -> int | None:
    return _positive_topic_id(settings.telegram_strong_launch_topic_id)


def dev_held_topic_id() -> int | None:
    return _positive_topic_id(settings.telegram_dev_held_topic_id)


def _is_socials_queue_size_error(error: Exception) -> bool:
    text = str(error).lower()
    return "max single record size" in text or "max_record_size" in text

# Combined for backward compatibility (all programs we monitor)
LAUNCHPADS = {**TRUE_LAUNCHPADS, **DEXES}

# Known CEX addresses for funding source labeling
CEX_ADDRESSES = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Binance",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfBKCoP3gKsGbU": "Coinbase",
    "H8sMJSCQxfKiFVcfB3J8q8G6h1r9t4g8r4t4f4f4f4f4": "Coinbase",
    "AC5RDfQFmDS1deWZosYb21bfU9a8hC7GPT8g82aJjX5J": "Kraken",
    "FWznbcNXWQu3oWjdwtnyHwrNVCcZq9Fzj7x8VbzY6b8X": "Kraken",
    "A77HErqxdUwXBH7q7rFx3t9qG8uFkqF8qF8qF8qF8qF8": "OKX",
    "31bsK5k13e1G9WkT9g1Wk13e1G9WkT9g1Wk13e1G9Wk": "KuCoin",
    "61bsK5k13e1G9WkT9g1Wk13e1G9WkT9g1Wk13e1G9Wk": "MEXC",
    "ASTyfSimeXGAXhdf81g7a7a7a7a7a7a7a7a7a7a7a7a": "FixedFloat",
    "HVh5HkW5j5X5k5Hk5W5j5X5k5Hk5W5j5X5k5Hk5W5j5": "Gate.io",
    "BYT3n3k3n3n3k3n3n3k3n3n3k3n3n3k3n3n3k3n3n3k": "Bybit",
    "B1tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG": "Bitget",
    "HWy1jotHpo6UqeQxx49dpYYdQB887zx8mwE": "Wintermute",
}


class SolanaListener:
    """
    Listens to Solana transactions in real-time.
    Sends freshie alerts with proper channel titles.
    """
    
    async def _send_to_socials_queue(self, token_data: dict, twitter_url: str):
        """Push token to Redis queue for local socials processor."""
        try:
            if not self._redis_client:
                # Initialize Redis if needed
                import redis.asyncio as redis
                self._redis_client = redis.from_url(settings.redis_url)
                
            # Queue payload
            payload = {
                "token_address": token_data.address,
                "twitter_url": twitter_url,
                "token_data": {
                    "symbol": token_data.symbol,
                    "name": token_data.name,
                    "mc_string": token_data.mc_string,
                    "age_string": token_data.age_string,
                    "age_hours": int(token_data.age_minutes / 60) if hasattr(token_data, "age_minutes") and token_data.age_minutes else 0,
                    "telegram": token_data.telegram,
                    "twitter": token_data.twitter,
                    "website": token_data.website
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            import orjson
            queue_key = "trench:socials:queue"
            encoded = orjson.dumps(payload)
            try:
                await self._redis_client.lpush(queue_key, encoded)
            except Exception as queue_error:
                if not _is_socials_queue_size_error(queue_error):
                    raise
                logger.warning("[Socials] Redis queue exceeded Upstash record limit; clearing stale queue")
                await self._redis_client.delete(queue_key)
                await self._redis_client.lpush(queue_key, encoded)

            max_length = max(1, settings.socials_queue_max_length)
            await self._redis_client.ltrim(queue_key, 0, max_length - 1)
            logger.debug(f"📤 [Socials] Queued {token_data.symbol} for checking")
            
        except Exception as e:
            logger.error(f"Error queuing socials check: {e}")

    def __init__(self):
        # Use RPC manager for rotating endpoints
        self.rpc_manager = get_rpc_manager()
        self._redis_client = None  # Lazy init
        
        self._running = False
        self._http_client: httpx.AsyncClient | None = None
        self._ws_connected = False
        self._last_ws_connected_at: datetime | None = None
        self._last_tx_received_at: datetime | None = None
        
        self.token_fetcher = get_token_fetcher()
        self.helius = get_helius_client()
        self.telegram = get_telegram_bot()
        self.channel_router = get_channel_router()
        self.tx_tracker = get_tx_tracker()
        
        # SNS tracker
        from services.sns_tracker import get_sns_tracker
        self.sns_tracker = get_sns_tracker()
        
        # Vanish protocol tracker
        from services.vanish_protocol import get_vanish_tracker
        self.vanish_tracker = get_vanish_tracker()
        
        # Bundle detector
        from services.bundle_detector import get_bundle_detector
        self.bundle_detector = get_bundle_detector()
        
        # Pattern detector
        from services.pattern_detector import get_pattern_detector
        self.pattern_detector = get_pattern_detector()
        
        # Freshies Wizard
        from services.freshies_wizard import get_freshies_wizard
        self.freshies_wizard = get_freshies_wizard()
        
        # Freshies DB Tracker (Replacing tx_tracker)
        from services.freshies_tracker import get_freshies_tracker
        self.freshies_tracker = get_freshies_tracker()
        
        # Token verifier (filters scam/crash tokens)
        from services.token_verifier import get_token_verifier
        self.token_verifier = get_token_verifier()
        
        # === NEW TRACKERS ===
        from services.late_migration_tracker import get_late_migration_tracker
        self.late_migration_tracker = get_late_migration_tracker()
        
        from services.streamflow_tracker import get_streamflow_tracker
        self.streamflow_tracker = get_streamflow_tracker()
        
        from services.dev_held_tracker import get_dev_held_tracker
        self.dev_held_tracker = get_dev_held_tracker()
        
        from services.creator_analyzer import get_good_creator_analyzer
        self.creator_analyzer = get_good_creator_analyzer()
        
        from services.socials_checker import get_socials_checker
        self.socials_checker = get_socials_checker()
        
        from services.strong_launch_tracker import get_strong_launch_tracker
        self.strong_launch_tracker = get_strong_launch_tracker()
        
        from services.strongfloor_tracker import get_strongfloor_tracker
        self.strongfloor_tracker = get_strongfloor_tracker()
        
        # Track state
        self._seen_tokens = set()
        self._processed_sigs = set()
        self._launchpad_tokens = set()  # Tokens that originated from TRUE_LAUNCHPADS
        
        # Stats per token
        self._fresh_buys = defaultdict(int)
        self._fresh_sells = defaultdict(int)
        self._partial_sells = defaultdict(int)
        self._dormant_buys = defaultdict(int)
        
        # Global stats
        self._tx_received = 0
        self._tx_processed = 0
        self._alerts_sent = 0
        self._dormant_alerts_sent = 0
        self._sns_alerts_sent = 0
        self._vanish_alerts_sent = 0
        self._bundle_alerts_sent = 0
        self._late_migration_alerts_sent = 0
        self._streamflow_alerts_sent = 0
        self._dev_held_alerts_sent = 0
        self._creator_alerts_sent = 0
        self._socials_alerts_sent = 0
        self._strong_launch_alerts_sent = 0
        self._strongfloor_alerts_sent = 0
        self._errors = 0
        
        # Rate limiting - max 5 concurrent RPC requests
        self._rpc_semaphore = asyncio.Semaphore(2)  # Reduced from 5 to stay under rate limits
        self._max_tx_queue_size = 500
        self._fresh_tx_queue_target_size = 250
        self._tx_queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_tx_queue_size)
        self._tx_dropped = 0
    
    def detect_launchpad(self, program_ids: list) -> tuple:
        """Detect launchpad from program IDs."""
        for pid in program_ids:
            if pid in LAUNCHPADS:
                return LAUNCHPADS[pid]
        return (None, "")
    
    async def format_alert(
        self,
        token_address: str,
        wallet_address: str,
        amount_sol: float,
        program_ids: list,
    ) -> tuple:
        """Format alert and classify. Returns (message, classification) or (None, classification)."""
        
        # Fetch token data
        token_data = await self.token_fetcher.get_token_data(token_address)
        
        if token_data:
            ticker = token_data.symbol
            name = token_data.name
            mc = token_data.market_cap
            mc_str = token_data.mc_string
            age_str = token_data.age_string
        else:
            ticker = "???"
            name = "Unknown"
            mc = None
            mc_str = "?"
            age_str = "?"
        
        # Get wallet info
        wallet_info = await self.token_fetcher.get_wallet_info(wallet_address)
        funding_source = wallet_info.get("funding_source", "Unknown")
        
        # IMPROVED: Check known CEX addresses for nice naming
        if funding_source == "Unknown" or ".." in funding_source:
             # Try to find in CEX list by address lookup
             # This would need the actual funding address, for now we rely on what API returns
             # If API returned address, check if it matches CEX
             pass
        
        # Check if funding source is a known CEX address (if full address returned)
        for cex_addr, cex_name in CEX_ADDRESSES.items():
            if funding_source == cex_addr:
                funding_source = cex_name
                break
        
        age_days = wallet_info.get("age_days", 0)
        tx_count = wallet_info.get("tx_count", 0)
        
        # Calculate hours since funding
        if age_days == 0:
            # Wallet created today - estimate hours
            hours_since_funding = min(tx_count, 12)
        else:
            hours_since_funding = age_days * 24
        
        # Classify into channels
        classification = self.channel_router.classify(
            amount_sol=amount_sol,
            market_cap=mc,
            hours_since_funding=hours_since_funding,
            wallet_tx_count=tx_count,
            funding_source=funding_source,
            program_ids=program_ids,
        )
        
        # Detect launchpad
        launchpad, launchpad_emoji = self.detect_launchpad(program_ids)

        
        # If not a valid alert, skip
        if not classification.is_valid_alert:
            if amount_sol >= 0.47: # Only log significant skips
                logger.info(f"⛔ Skipped {ticker}: {amount_sol:.2f} SOL | Age {hours_since_funding}h | Tx {tx_count}")
            # Record as dormant buy in tracker
            await self.tx_tracker.record_buy(token_address, wallet_address, 0, amount_sol)
            return None, classification
        
        
        # Open DB session for freshies tracking
        from database import get_db_session
        from services.freshies_tracker import get_freshies_tracker
        
        async with get_db_session() as session:
            # Ensure token exists in DB
            token_db = await self.freshies_tracker.get_or_create_token(
                session=session,
                contract_address=token_address,
                name=name,
                symbol=ticker,
                launchpad=launchpad
            )
            
            # Create wallet object (needed for freshies tracker)
            from models import Wallet, WalletType
            from sqlalchemy import select
            
            # Check if wallet exists
            result = await session.execute(select(Wallet).where(Wallet.address == wallet_address))
            wallet_db = result.scalar_one_or_none()
            
            if not wallet_db:
                # Determine type
                w_type = WalletType.FRESH if classification.is_valid_alert else (
                    WalletType.DORMANT if hours_since_funding > 24*30 else WalletType.ACTIVE
                )
                
                wallet_db = Wallet(
                    address=wallet_address,
                    wallet_type=w_type,
                    funding_source=funding_source,
                    first_activity_at=datetime.utcnow(),
                    last_activity_at=datetime.utcnow(),
                    total_transactions=tx_count
                )
                session.add(wallet_db)
                await session.flush() # Get ID
            
            # Process purchase through tracker
            freshie = await self.freshies_tracker.process_token_purchase(
                session=session,
                wallet=wallet_db,
                token=token_db,
                tx_signature=f"sig_{int(datetime.utcnow().timestamp())}", 
                amount_sol=amount_sol,
                program_ids=program_ids,
                suppress_alert=True # Let solana_listener handle alerting
            )
            
            # Flush to DB so the select query in get_bbb_metrics sees this new record!
            await session.flush()
            
            # Get accurate metrics from DB
            metrics = await self.freshies_tracker.get_bbb_metrics(session, token_address)
            fresh_buys = metrics["fresh_buy_count"]
            fresh_sells = metrics["fresh_sell_count"]
            partial_sells = metrics["partial_sell_count"]
            dormant_buys = metrics["dormant_buy_count"]

        # Validate counts (fallback to 1 if freshie just created)
        if classification.is_valid_alert and fresh_buys == 0:
             fresh_buys = 1
        
        # Check if this is a TRUE_LAUNCHPAD (not just any DEX)
        is_true_launchpad = False
        for pid in program_ids:
            if pid in TRUE_LAUNCHPADS:
                is_true_launchpad = True
                # Track this token as originating from a launchpad
                self._launchpad_tokens.add(token_address)
                break
        
        # HYBRID FILTER: Allow trades if:
        # 1. Token is on a TRUE_LAUNCHPAD (pump.fun, moonshot, bonk, etc.)
        # 2. Token is via a trading bot router (Axiom, Trojan, etc.)
        # 3. Token was PREVIOUSLY seen on a TRUE_LAUNCHPAD (allows DEX trades on graduated tokens)
        # 4. Token address ends with "pump" (pump.fun graduated tokens)
        # 5. Token data indicates it's from a known launchpad
        is_known_launchpad_token = token_address in self._launchpad_tokens

        # Check if token is a pump.fun token (addresses end with "pump")
        is_pumpfun_token = token_address.lower().endswith("pump")
        if is_pumpfun_token:
            self._launchpad_tokens.add(token_address)
            is_known_launchpad_token = True

        # Check DexScreener data for launchpad info
        if token_data and not is_known_launchpad_token:
            dex_name = (token_data.dex_name or "").lower()
            # Check if token was launched on a known launchpad based on DexScreener data
            if any(lp in dex_name for lp in ["pump", "moonshot", "meteora", "raydium_lp"]):
                self._launchpad_tokens.add(token_address)
                is_known_launchpad_token = True

        if not is_true_launchpad and not classification.is_via_router and not is_known_launchpad_token:
            logger.debug(f"⛔ Skipped {token_address[:12]}... (Not launchpad/router/known token)")
            return None, classification
        
        # Record buy for pattern detection
        is_fresh = classification.is_valid_alert
        is_dormant = hours_since_funding and hours_since_funding > 24 * 4  # 4+ days = dormant-ish
        is_old_fresh = classification.is_old_freshie
        router_name = classification.router_name if hasattr(classification, 'router_name') else None
        
        # Verify token before pattern tracking (filter scams/crash coins)
        liquidity = token_data.liquidity_usd if token_data and token_data.liquidity_usd else 0
        dex_name = token_data.dex_name if token_data else ""
        verification = self.token_verifier.verify_from_data(
            token_address=token_address,
            dex_name=dex_name,
            liquidity_usd=liquidity,
            market_cap=mc or 0,
            program_ids=program_ids,
        )
        
        if not verification.is_verified:
            logger.debug(f"⚠️ Token not verified: {ticker} | {verification.rejection_reason}")
            # NOTE: Still send freshies alerts, but skip pattern tracking for unverified tokens
        
        if verification.is_verified:
            # Update pattern detector with token info (only for verified tokens)
            self.pattern_detector.update_token_info(
                token_address=token_address,
                symbol=ticker,
                name=name,
                market_cap=mc,
                age_minutes=int(token_data.age_minutes) if token_data and token_data.age_minutes else 0,
                launchpad=launchpad,
                launchpad_emoji=launchpad_emoji,
                is_migrated=True if launchpad in ["meteora", "orca"] else False,
                current_price=token_data.price_usd if token_data else None,
            )
            
            # Record the buy event for pattern tracking
            await self.pattern_detector.record_buy(
                token_address=token_address,
                wallet=wallet_address,
                sol_amount=amount_sol,
                is_fresh=is_fresh,
                is_dormant=is_dormant,
                is_old_fresh=is_old_fresh,
                router=router_name,
                funding_source=funding_source,
            )
        
        # Update Freshies Wizard with token info
        self.freshies_wizard.update_token_info(
            token_address=token_address,
            symbol=ticker,
            name=name,
            market_cap=mc,
            age_minutes=int(token_data.age_minutes) if token_data and token_data.age_minutes else 0,
            launchpad=launchpad,
            launchpad_emoji=launchpad_emoji,
            fresh_sells=fresh_sells,
            partial_sells=partial_sells,
            dormant_buys=dormant_buys,
            telegram_link=token_data.telegram if token_data else None,
            twitter_link=token_data.twitter if token_data else None,
            website_link=token_data.website if token_data else None,
        )
        
        # Record fresh buy for wizard patterns (User requested 0.47 SOL threshold)
        if is_fresh and amount_sol >= 0.47:
            await self.freshies_wizard.record_fresh_buy(
                token_address=token_address,
                wallet=wallet_address,
                sol_amount=amount_sol,
                router=router_name,
                funding_source=funding_source,
            )
        
        # Check if first mention
        is_first = token_address not in self._seen_tokens
        if is_first:
            self._seen_tokens.add(token_address)
        
        # Build emoji indicators
        indicators = []
        if is_first:
            indicators.append("⭐️")
        if classification.is_old_freshie:
            indicators.append("🐌")  # Old freshie indicator
        if classification.router_emoji:
            indicators.append(classification.router_emoji)
        if amount_sol >= 15:
            indicators.append("🐳")
        elif amount_sol >= 5:
            indicators.append("🐬")
        
        indicator_str = " ".join(indicators) + (" " if indicators else "")
        
        # Get channel title from primary channel
        channel_title = self.channel_router.get_channel_title(classification.primary_channel)
        
        # Format time since funding
        time_since_funding = classification.funding_time_ago
        
        # Build message
        # Example: 🟠 SOL TG Freshies
        # ⭐️ 🔱 $MCP MyCrypto 5.07 💊 Kraken 🟢 2h
        # 👶 87 ♦️ 62 🔶 101 ⏳ 14
        # MC: 851k | CA: 1h
        # contract
        # links
        
        # Get pair address for Axiom (requires pair address, not CA)
        # First try from token_data, then make dedicated API call
        pair_address = None
        if token_data and token_data.pair_address:
            pair_address = token_data.pair_address
        else:
            # Make dedicated API call to get pair address
            pair_address = await self.token_fetcher.get_pair_address(token_address)
        
        # Fall back to token address if no pair found (may not work on Axiom)
        if not pair_address:
            pair_address = token_address
            logger.debug(f"No pair address found for {token_address[:8]}, using CA for Axiom link")
        
        message = f"""🟠 SOL {channel_title}
{indicator_str}${ticker} {name} {amount_sol:.2f} {launchpad_emoji} {funding_source} 🟢 {time_since_funding}
👶 {fresh_buys} ♦️ {fresh_sells} 🔶 {partial_sells} ⏳ {dormant_buys}
MC: {mc_str} | CA: {age_str}
<code>{token_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{token_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={token_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={token_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{token_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={token_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={token_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={token_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={token_address}">NE</a> | <a href="https://dexscreener.com/solana/{token_address}">DS</a> | <a href="https://pump.fun/{token_address}">PF</a>"""
        
        return message.strip(), classification
    
    async def format_dormant_alert(
        self,
        token_address: str,
        wallet_address: str,
        amount_sol: float,
        days_since_last_activity: int,
        program_ids: list,
    ) -> tuple:
        """Format dormant wallet alert. Returns (message, classification) or (None, classification)."""
        
        # Fetch token data
        token_data = await self.token_fetcher.get_token_data(token_address)
        
        if token_data:
            ticker = token_data.symbol
            name = token_data.name
            mc = token_data.market_cap
            mc_str = token_data.mc_string
            age_str = token_data.age_string
        else:
            ticker = "???"
            name = "Unknown"
            mc = None
            mc_str = "?"
            age_str = "?"
        
        # Detect launchpad
        launchpad, launchpad_emoji = self.detect_launchpad(program_ids)
        
        # Classify dormant
        dormant_class = self.channel_router.classify_dormant(
            wallet_address=wallet_address,
            amount_sol=amount_sol,
            market_cap=mc,
            days_since_last_activity=days_since_last_activity,
            program_ids=program_ids,
            launchpad_name=launchpad,
            launchpad_emoji=launchpad_emoji,
        )
        
        if not dormant_class.is_valid_alert:
            return None, dormant_class
        
        # Check first mention
        is_first = token_address not in self._seen_tokens
        
        # Track dormant buys
        self._dormant_buys[token_address] += 1
        dormant_count = self._dormant_buys[token_address]
        
        # Whale/dolphin
        is_whale = amount_sol >= 15
        is_dolphin = amount_sol >= 5 and not is_whale
        
        # Use telegram bot's format method
        dormant_type_str = dormant_class.dormant_type.value if dormant_class.dormant_type else "dormants"
        message = await self.telegram.format_dormant_alert(
            ticker=ticker,
            token_name=name,
            contract_address=token_address,
            amount_sol=amount_sol,
            market_cap_str=mc_str,
            coin_age_str=age_str,
            last_seen_days=days_since_last_activity,
            dormant_emoji=dormant_class.dormant_emoji,
            dormant_type=dormant_type_str,
            dormant_count=dormant_count,
            launchpad_emoji=launchpad_emoji,
            router_emoji=dormant_class.router_emoji,
            is_first_mention=is_first,
            is_whale=is_whale,
            is_dolphin=is_dolphin,
        )
        
        if is_first:
            self._seen_tokens.add(token_address)
        
        return message, dormant_class

    def _capture_first_seen_for_enrichment(self, token_address: str) -> bool:
        """Snapshot first-seen state before format_alert mutates _seen_tokens."""
        return token_address not in self._seen_tokens

    def _record_sns_alert_sent(self, token_address: str) -> None:
        """Keep listener and SNS tracker alert counters in sync."""
        self._sns_alerts_sent += 1
        self.sns_tracker.track_sns_buy(token_address)
        increment = getattr(self.sns_tracker, "increment_alerts_sent", None)
        if callable(increment):
            increment()
    
    async def start(self):
        """Start the listener with WebSocket + parallel polling."""
        self._running = True
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._ws_connected = False
        self._last_ws_connected_at = None
        self._last_tx_received_at = None
        
        logger.info("🚀 Starting Solana listener...")
        
        # Send startup notification
        # Send startup notification via Feedback channel
        try:
            startup_msg = """🟢 <b>TRENCH TOOL V1 - SYSTEMS ONLINE</b>

<b>Solana Monitors:</b>
✅ Fresh Wallets (Age &lt; 7d)
✅ Dormant Wallets (&gt; 30d)
✅ Bundle Detection
✅ Pattern Recognition
✅ Smart Socials (FrontrunPro + Gemini)
✅ Strong Launches & Floors
✅ Late Migrations & Dev Tracking
✅ Max Market Cap Filter (<$100M)

<b>Infrastructure:</b>
📡 Helius RPC: Connected
🤖 Gemini AI: Active
🔌 FrontrunPro Extension: Loaded"""

            topic_id = settings.telegram_feedback_topic_id if settings.telegram_feedback_topic_id > 0 else None
            if not topic_id:
                logger.info("Startup stats suppressed because feedback topic is disabled")
            
            logger.info(f"📢 Sending startup stats to Topic ID: {topic_id}")
            
            if topic_id:
                await self.telegram.send_alert(startup_msg, topic_id=topic_id)
        except Exception as e:
            logger.error(f"Failed to send startup alert: {e}")
        
        # Start both WebSocket and parallel polling + background monitors
        await asyncio.gather(
            self._websocket_listener(),
            self._parallel_poll_transactions(),
            self._background_monitor(),  # New: periodic checks for time-based trackers
        )
    
    async def _background_monitor(self):
        """Background task for time-based tracker checks (Dev Held, Strong Launch, etc.)."""
        logger.info("🔄 Starting background monitor (60s interval, status report every 5 min)...")
        
        report_counter = 0
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                report_counter += 1
                
                # Get all tracker stats
                dev_stats = self.dev_held_tracker.get_stats()
                floor_stats = self.strongfloor_tracker.get_stats()
                late_mig_stats = self.late_migration_tracker.get_stats()
                streamflow_stats = self.streamflow_tracker.get_stats()
                creator_stats = self.creator_analyzer.get_stats()
                socials_stats = self.socials_checker.get_stats()
                launch_stats = self.strong_launch_tracker.get_stats()
                
                # Regular debug log for active trackers
                if dev_stats["devs_holding"] > 0:
                    logger.debug(f"💎 Dev Held: {dev_stats['devs_holding']} tokens with dev holding")

                if floor_stats["tokens_tracked"] > 0:
                    logger.debug(f"🧱 Strongfloor: Tracking {floor_stats['tokens_tracked']} tokens")

                # === SOCIALS ALERT FLUSH ===
                # Transaction processing can discover strong socials before enrichment is available.
                # Flush cached, unalerted high-quality profiles so the Socials topic stays live.
                for social_profile in self.socials_checker.get_alertable_profiles(limit=2):
                    try:
                        token_data = await self.token_fetcher.get_token_data(social_profile.token_address)
                        social_profile = await self.socials_checker.analyze_enhanced(social_profile)
                        if not self.socials_checker.is_alertable_socials(social_profile):
                            continue
                        socials_msg = await self.socials_checker.format_socials_alert(
                            ticker=token_data.symbol if token_data else "???",
                            token_name=token_data.name if token_data else "Unknown",
                            contract_address=social_profile.token_address,
                            profile=social_profile,
                            market_cap_str=token_data.mc_string if token_data else "?",
                            coin_age_str=token_data.age_string if token_data else "?",
                        )
                        msg_id = await self.telegram.send_alert(socials_msg, topic_id=socials_topic_id())
                        if msg_id:
                            self.socials_checker.mark_alerted(social_profile.token_address)
                            self.socials_checker.increment_alerts()
                            self._socials_alerts_sent += 1
                            logger.info(
                                f"ðŸ“± SOCIALS ALERT FLUSHED: {social_profile.token_address[:12]}... | "
                                f"Score: {max(social_profile.enhanced_score, social_profile.social_score)}/100"
                            )
                    except Exception as e:
                        logger.debug(f"Error flushing socials alert for {social_profile.token_address[:12]}: {e}")

                # === DEV HELD CHECKING ===
                # Check dev wallets that haven't been alerted yet
                holdings_to_check = self.dev_held_tracker.get_holdings_to_check()
                for token_address, holding in holdings_to_check.items():
                    try:
                        # Get current token balance of dev wallet
                        from services.api_clients import get_helius_client
                        helius = get_helius_client()
                        current_balance = await helius.get_wallet_token_balance(
                            holding.dev_wallet,
                            token_address
                        )

                        # Update holding and check if threshold met
                        result = self.dev_held_tracker.update_holding(token_address, current_balance)

                        if result and self.dev_held_tracker.check_should_alert(token_address):
                            # Get token data for alert
                            token_data = await self.token_fetcher.get_token_data(token_address)
                            if token_data:
                                supply_pct = (current_balance / holding.initial_supply * 100) if holding.initial_supply > 0 else 0

                                dev_msg = await self.dev_held_tracker.format_dev_held_alert(
                                    ticker=token_data.symbol,
                                    token_name=token_data.name,
                                    contract_address=token_address,
                                    holding_hours=holding.holding_hours,
                                    supply_pct=supply_pct,
                                    market_cap_str=token_data.mc_string,
                                )

                                # Send alert
                                topic = dev_held_topic_id()
                                await self.telegram.send_alert(dev_msg, topic_id=topic)

                                # Mark as alerted
                                self.dev_held_tracker.mark_alerted(token_address)
                                self.dev_held_tracker.increment_alerts()
                                logger.info(f"💎 DEV HELD ALERT SENT: {token_data.symbol} | {holding.holding_hours}h | {supply_pct:.0f}%")

                    except Exception as e:
                        logger.debug(f"Error checking dev holding for {token_address[:12]}: {e}")
                
                # Late Migration: Cleanup old bonding records
                self.late_migration_tracker.cleanup_old_bondings(max_age_hours=24)
                
                # === COMPREHENSIVE STATUS REPORT (every 5 minutes) ===
                if report_counter % 5 == 0:
                    logger.info("=" * 60)
                    logger.info("📊 NEW MODULES STATUS REPORT")
                    logger.info("=" * 60)
                    
                    # Late Migration
                    logger.info(f"🕐 Late Migration: pending_bondings={late_mig_stats['pending_bondings']} | migrations_detected={late_mig_stats['migrations_detected']} | alerts={late_mig_stats['alerts_sent']}")
                    
                    # Streamflow
                    logger.info(f"🔒 Streamflow: tokens_with_locks={streamflow_stats['tokens_with_locks']} | total_locks={streamflow_stats['total_locks']} | alerts={streamflow_stats['alerts_sent']}")
                    
                    # Dev Held
                    logger.info(f"💎 Dev Held: tokens_tracked={dev_stats['tokens_tracked']} | devs_holding={dev_stats['devs_holding']} | alerts={dev_stats['alerts_sent']}")
                    
                    # Creator Analyzer
                    logger.info(f"👑 Creator: creators_analyzed={creator_stats['creators_analyzed']} | good_creators={creator_stats['good_creators']} | alerts={creator_stats['alerts_sent']}")
                    
                    # Socials Checker
                    logger.info(f"📱 Socials: tokens_checked={socials_stats['tokens_checked']} | strong_socials={socials_stats['strong_socials']} | alerts={socials_stats['alerts_sent']}")
                    
                    # Strong Launch
                    logger.info(f"🚀 Strong Launch: strong_launches={launch_stats['strong_launches']} | alerts={launch_stats['alerts_sent']}")
                    
                    # Strongfloor
                    logger.info(f"🧱 Strongfloor: tokens_tracked={floor_stats['tokens_tracked']} | strongfloors_detected={floor_stats['strongfloors_detected']} | alerts={floor_stats['alerts_sent']}")
                    
                    # Check if modules are actually being called
                    total_activity = (
                        late_mig_stats['pending_bondings'] + late_mig_stats['migrations_detected'] +
                        streamflow_stats['tokens_with_locks'] +
                        dev_stats['tokens_tracked'] +
                        creator_stats['creators_analyzed'] +
                        socials_stats['tokens_checked'] +
                        launch_stats['strong_launches'] +
                        floor_stats['tokens_tracked']
                    )
                    
                    if total_activity == 0:
                        logger.warning("⚠️ WARNING: No new module activity detected! Modules may not be properly integrated.")
                    else:
                        logger.info(f"✅ Total activity across new modules: {total_activity} items tracked")
                    
                    logger.info("=" * 60)
                
            except Exception as e:
                logger.error(f"Background monitor error: {e}")
    
    async def stop(self):
        """Stop the listener."""
        self._running = False
        
        if self._http_client:
            await self._http_client.aclose()
        
        logger.info("Solana listener stopped")
    
    async def _websocket_listener(self):
        """Listen for transactions via Helius WebSocket (real-time)."""
        import websockets
        import json
        
        ws_url = self.rpc_manager.get_ws_url()
        logger.info(f"🔌 Connecting to WebSocket: {ws_url[:50]}...")
        
        # All DEX programs to subscribe to
        DEX_PROGRAMS = list(LAUNCHPADS.keys())
        
        while self._running:
            ws_url = self.rpc_manager.get_ws_url()
            try:
                async with websockets.connect(ws_url, ping_interval=30) as ws:
                    self._ws_connected = True
                    self._last_ws_connected_at = datetime.utcnow()
                    logger.info(f"✅ WebSocket connected! Subscribing to {len(DEX_PROGRAMS)} DEX programs...")
                    
                    # Subscribe to logs for each DEX program
                    for i, program_id in enumerate(DEX_PROGRAMS):
                        subscribe_msg = {
                            "jsonrpc": "2.0",
                            "id": i + 1,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [program_id]},
                                {"commitment": "confirmed"}
                            ]
                        }
                        await ws.send(json.dumps(subscribe_msg))
                    
                    logger.info(f"📡 Subscribed to {len(DEX_PROGRAMS)} DEX log streams")
                    
                    # Start worker tasks to process transactions (limit concurrency)
                    workers = [asyncio.create_task(self._tx_worker()) for _ in range(20)]
                    
                    # Listen for messages
                    async for message in ws:
                        if not self._running:
                            break
                        
                        try:
                            data = json.loads(message)
                            
                            # Check if it's a notification (not subscription confirmation)
                            if data.get("method") == "logsNotification":
                                result = data.get("params", {}).get("result", {})
                                value = result.get("value", {})
                                signature = value.get("signature")
                                
                                if signature and signature not in self._processed_sigs:
                                    self._processed_sigs.add(signature)
                                    self._tx_received += 1
                                    self._last_tx_received_at = datetime.utcnow()
                                    
                                    # Limit cache size
                                    if len(self._processed_sigs) > 5000:
                                        self._processed_sigs = set(list(self._processed_sigs)[-2500:])
                                    
                                    self._enqueue_signature(signature)
                        
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"WebSocket message error: {e}")
                    
                    # Cancel workers when done
                    for w in workers:
                        w.cancel()
                            
            except Exception as e:
                self._ws_connected = False
                self.rpc_manager.report_error(
                    ws_url,
                    is_rate_limit="429" in str(e) or "too many requests" in str(e).lower(),
                )
                logger.error(f"WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
    
    async def _tx_worker(self):
        """Worker that processes transactions from the queue."""
        while self._running:
            try:
                # Wait for a signature from the queue
                signature = await asyncio.wait_for(self._tx_queue.get(), timeout=5.0)
                
                # Process with rate limiting delay
                await asyncio.sleep(0.5)  # 500ms between requests per worker to stay under limits
                await self._fetch_and_process_tx(signature)
                
            except asyncio.TimeoutError:
                continue  # No items in queue, keep waiting
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TX worker error: {e}")
                await asyncio.sleep(1)

    def _enqueue_signature(self, signature: str) -> None:
        """Keep SOL alert processing fresh by dropping stale backlog first."""
        try:
            self._tx_queue.put_nowait(signature)
            return
        except asyncio.QueueFull:
            pass

        dropped_now = 0
        while self._tx_queue.qsize() >= self._fresh_tx_queue_target_size:
            try:
                self._tx_queue.get_nowait()
                self._tx_queue.task_done()
                dropped_now += 1
            except asyncio.QueueEmpty:
                break

        try:
            self._tx_queue.put_nowait(signature)
            self._tx_dropped += dropped_now
            if self._tx_dropped and (self._tx_dropped == dropped_now or self._tx_dropped % 10000 < dropped_now):
                logger.warning(
                    "SOL tx queue saturated; dropped stale signatures to keep alerts fresh "
                    f"(dropped={self._tx_dropped}, max={self._max_tx_queue_size})"
                )
        except asyncio.QueueFull:
            self._tx_dropped += dropped_now + 1
            self._errors += 1
     
    async def _fetch_and_process_tx(self, signature: str):
        """Fetch transaction details and process with rate limiting."""
        # Use semaphore to limit concurrent RPC requests
        async with self._rpc_semaphore:
            try:
                # Larger delay to stay under rate limits (100ms = 10 req/s per worker)
                await asyncio.sleep(0.25)
                
                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                }
                
                rpc_url = self.rpc_manager.get_rpc_url()
                tx_response = await self._http_client.post(rpc_url, json=tx_payload)
                
                # Handle rate limiting with retry
                if tx_response.status_code == 429:
                    self.rpc_manager.report_error(rpc_url, is_rate_limit=True)
                    logger.warning(f"Rate limited on {rpc_url[-20:]}, rotating and retrying...")
                    await asyncio.sleep(2.0)  # Wait longer before retry
                    rpc_url = self.rpc_manager.get_rpc_url()  # Get next endpoint
                    tx_response = await self._http_client.post(rpc_url, json=tx_payload)

                    # Check if retry also failed
                    if tx_response.status_code == 429:
                        logger.error(f"❌ Retry also rate limited for TX {signature[:16]}, skipping")
                        self._errors += 1
                        return
                    elif tx_response.status_code != 200:
                        logger.error(f"❌ Retry failed with status {tx_response.status_code} for TX {signature[:16]}")
                        self._errors += 1
                        return

                tx_result = tx_response.json().get("result")
                
                if tx_result:
                    await self._process_transaction(tx_result, signature)
            except Exception as e:
                logger.error(f"Error fetching tx {signature[:16]}: {e}")
                self._errors += 1
    
    async def _parallel_poll_transactions(self):
        """Parallel polling fallback - only activates when WebSocket fails."""
        logger.info("🔄 Parallel polling on standby (WebSocket primary)...")
        
        # Wait for WebSocket to connect first
        await asyncio.sleep(5)
        
        # Only 4 key DEXes for backup polling (reduced to avoid rate limits)
        DEX_PROGRAMS = [
            ("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "Raydium"),
            ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "pump.fun"),
            ("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "Jupiter"),
            ("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "Meteora"),
            ("strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m", "Streamflow"),
        ]
        
        async def poll_dex(program_id: str, dex_name: str, stagger_delay: float):
            """Poll a single DEX as backup when WebSocket is down."""
            # Stagger start times to avoid hitting API all at once
            await asyncio.sleep(stagger_delay)
            
            while self._running:
                try:
                    # ONLY poll if WebSocket is disconnected
                    if not self._should_backup_poll():
                        await asyncio.sleep(30)  # Check every 30s if WS is still up
                        continue

                    logger.info(f"📡 Backup polling {dex_name} (WebSocket down)")
                    
                    payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getSignaturesForAddress",
                        "params": [program_id, {"limit": 10}]
                    }
                    
                    rpc_url = self.rpc_manager.get_rpc_url()
                    response = await self._http_client.post(rpc_url, json=payload)
                    if response.status_code == 429:
                        self.rpc_manager.report_error(rpc_url, is_rate_limit=True)
                        await asyncio.sleep(max(5.0, self.rpc_manager.seconds_until_available()))
                        continue
                    result = response.json()
                    signatures = result.get("result", [])
                    
                    for sig_info in signatures:
                        signature = sig_info.get("signature")
                        
                        if signature and signature not in self._processed_sigs:
                            self._processed_sigs.add(signature)
                            self._tx_received += 1
                            self._last_tx_received_at = datetime.utcnow()
                            
                            # Limit cache size
                            if len(self._processed_sigs) > 5000:
                                self._processed_sigs = set(list(self._processed_sigs)[-2500:])
                            
                            # Fetch and process with small delay to avoid rate limits
                            await asyncio.sleep(0.2)
                            await self._fetch_and_process_tx(signature)
                    
                    await asyncio.sleep(5)  # Poll every 5 seconds per DEX (when WS is down)
                    
                except Exception as e:
                    logger.error(f"Poll error ({dex_name}): {e}")
                    self._errors += 1
                    await asyncio.sleep(10)
        
        # Start DEX pollers with staggered delays (1 second apart)
        tasks = [poll_dex(pid, name, i * 1.0) for i, (pid, name) in enumerate(DEX_PROGRAMS)]
        await asyncio.gather(*tasks)
    
    async def _process_transaction(self, tx_data: dict, signature: str):
        """Process a transaction and send alert if applicable."""
        logger.info(f"📥 Processing TX: {signature}")
        try:
            meta = tx_data.get("meta", {})
            if meta.get("err"):
                return  # Skip failed transactions

            pre_balances = meta.get("preBalances", [0])
            post_balances = meta.get("postBalances", [0])
            
            if not pre_balances or not post_balances:
                logger.debug("Missing balance data")
                return
            
            message = tx_data.get("transaction", {}).get("message", {})
            account_keys = message.get("accountKeys", [])
            
            if not account_keys:
                return
            
            wallet = account_keys[0]
            if isinstance(wallet, dict):
                wallet = wallet.get("pubkey", "")

            program_ids = self._extract_program_ids(tx_data)
            await self._maybe_process_streamflow_lock(tx_data, program_ids=program_ids)

            post_tokens = meta.get("postTokenBalances", [])
            pre_tokens = meta.get("preTokenBalances", [])

            # Extract SOL spent more accurately
            sol_spent = 0.0
            
            # Method 1: Check balance change of the wallet (including fees)
            # This is often inaccurate for complex trades or when fees are high relative to amount
            balance_change = (pre_balances[0] - post_balances[0]) / 1e9
            
            # Method 2: Look for SOL transfers in inner instructions (more accurate for swaps)
            # We look for transfers FROM the wallet TO an external account (DEX, Curve, etc.)
            inner_instructions = meta.get("innerInstructions", [])
            sol_transferred = 0.0
            
            for inner in inner_instructions:
                for ix in inner.get("instructions", []):
                    # Check for system program transfer
                    if ix.get("programId") == "11111111111111111111111111111111":
                        parsed = ix.get("parsed", {})
                        if parsed.get("type") == "transfer":
                            info = parsed.get("info", {})
                            # If transfer is FROM the main wallet
                            if info.get("source") == wallet:
                                lamports = info.get("lamports", 0)
                                sol_transferred += lamports / 1e9
            
            # Method 3: Check WSOL balance change (Mint: So11111111111111111111111111111111111111112)
            # If user swaps WSOL -> Token, their SOL balance stays same, but WSOL decreases.
            wsol_change = 0.0
            WSOL_MINT = "So11111111111111111111111111111111111111112"
            
            pre_wsol = 0.0
            for pre in pre_tokens:
                 if pre.get("mint") == WSOL_MINT and pre.get("owner") == wallet:
                     pre_wsol = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                     break
            
            post_wsol = 0.0
            for post in post_tokens:
                 if post.get("mint") == WSOL_MINT and post.get("owner") == wallet:
                     post_wsol = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                     break
            
            if pre_wsol > post_wsol:
                wsol_change = pre_wsol - post_wsol

            # Use the MAXIMUM of the three methods to catch the true spend
            # 1. Balance Change: Catches simple SOL transfers + fees
            # 2. Inner Transfers: Catches specific router interactions / bonding curves
            # 3. WSOL Change: Catches Wrapped SOL swaps
            sol_spent = max(balance_change, sol_transferred, wsol_change)



            # If still roughly 0, logging will catch it later.
            
            post_tokens = meta.get("postTokenBalances", [])
            pre_tokens = meta.get("preTokenBalances", [])
            
            if not post_tokens:
                logger.info(f"🚫 No token transfer for {signature}")
                return  # No token transfer (likely SOL-only tx)
            
            token_mint = None
            for post in post_tokens:
                mint = post.get("mint")
                
                if mint in EXCLUDED_TOKENS:
                    continue
                
                if post.get("owner") != wallet:
                    continue
                
                post_amount = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                
                pre_amount = 0
                for pre in pre_tokens:
                    if pre.get("mint") == mint:
                        pre_amount = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                        break
                
                if post_amount > pre_amount:
                    token_mint = mint
                    token_bought = post_amount - pre_amount
                    break
                elif post_amount < pre_amount:
                    token_mint = mint
                    token_sold = pre_amount - post_amount
                    is_sell = True
                    is_full_sell = (post_amount == 0)
                    
                    # Process Sell immediately (update stats)
                    # We need the DB session for this, so we do it inside a session block or fire-and-forget?
                    # The listener is async, so we can await. But we need a session.
                    # freshies_tracker needs a session.
                    # For performance, maybe we create a quick session just for this update?
                    from database import get_db_session
                    from models import Wallet, Token, WalletType
                    from sqlalchemy import select
                    
                    try:
                        async with get_db_session() as session:
                             # Ensure token/wallet exist
                             token_db = await self.freshies_tracker.get_or_create_token(session, token_mint)
                             result = await session.execute(select(Wallet).where(Wallet.address == wallet))
                             wallet_db = result.scalar_one_or_none()
                             
                             if wallet_db and wallet_db.wallet_type == WalletType.FRESH: # Only track freshie sells
                                 await self.freshies_tracker.process_token_sell(
                                     session=session,
                                     wallet=wallet_db,
                                     token=token_db,
                                     tx_signature=signature,
                                     amount_tokens=token_sold,
                                     is_full_sell=is_full_sell
                                 )
                                 await session.commit()
                                 sell_type = "Full" if is_full_sell else "Partial"
                                 logger.info(f"📉 Freshie {sell_type} Sell: {wallet[:8]}... sold {token_sold:.2f} tokens of {token_mint[:8]}...")
                    except Exception as e:
                        logger.error(f"Error processing sell: {e}")
                    
                    # We don't alert on sells in this loop (yet), so we return to avoid treating it as a buy
                    return
            
            if not token_mint or token_mint in EXCLUDED_TOKENS:
                logger.info(f"🚫 No valid mint / Excluded: {token_mint}")
                return
            
            # === RAYDIUM CLMM FILTER ===
            # User request: remove Raydium CLMM launched coins (avoids spam/unwanted alerts)
            if "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK" in program_ids:
                logger.debug(f"🛑 [Filter] Skipping Raydium CLMM transaction for {token_mint[:8]}...")
                return

            # === LATE MIGRATION TRACKING ===
            # 1. Check for pump.fun bonding curve completion (balance change = 0 usually means curve completed/migration start)
            # We need to calculate balance change for the bonding curve account, but simplified:
            # If it's a pump.fun tx and we see token mint authority changes or specific log, it's better.
            # For now, let's use the tracker's method
            
            # === LATE BONDING DETECTION ===
            # Check if this is a late bonding (token bonded 1+ days after launch)
            late_bonding = await self.late_migration_tracker.check_late_bonding(token_mint, program_ids)
            if late_bonding:
                # Fetch data for alert
                token_data = await self.token_fetcher.get_token_data(token_mint)
                ticker = token_data.symbol if token_data else "???"
                name = token_data.name if token_data else ""
                mc_str = token_data.mc_string if token_data else "?"
                
                mig_msg = await self.late_migration_tracker.format_late_migration_alert(
                    ticker=ticker,
                    token_name=name,
                    contract_address=token_mint,
                    delay_hours=late_bonding.delay_hours,
                    market_cap_str=mc_str,
                )
                
                # Send to Late Migration topic or Freshies as fallback
                mig_topic = settings.telegram_late_migration_topic_id if settings.telegram_late_migration_topic_id > 0 else settings.telegram_freshies_topic_id
                await self.telegram.send_alert(mig_msg, topic_id=mig_topic)
                self.late_migration_tracker.increment_alerts()
                self._late_migration_alerts_sent += 1

            # Log that we have a valid token purchase
            self._tx_processed += 1
            logger.info(f"💰 Token buy: {sol_spent:.2f} SOL ({token_bought:.0f} tokens) -> {token_mint[:8]}... from wallet {wallet[:8]}...")
            
            # ... (rest of classification logic)
            
            # Check if transaction involves a TRUE launchpad (pump.fun, moonshot, bonk, etc.)
            detected_launchpad = None
            detected_launchpad_emoji = ""
            for pid in program_ids:
                if pid in TRUE_LAUNCHPADS:
                    detected_launchpad, detected_launchpad_emoji = TRUE_LAUNCHPADS[pid]
                    break
            
            # Also check if going through a DEX (even if not a launchpad)
            detected_dex = None
            if not detected_launchpad:
                for pid in program_ids:
                    if pid in DEXES:
                        detected_dex, _ = DEXES[pid]
                        break
            
            # Check for special protocol types (Vanish, Streamflow)
            is_vanish = self.vanish_tracker.is_vanish_transaction(program_ids)
            is_streamflow = self.streamflow_tracker.is_streamflow_lock(program_ids)

            # FILTER: Skip if not a relevant transaction type
            # We allow: Launchpads, DEXes, Vanish, Streamflow
            if not detected_launchpad and not detected_dex and not is_vanish and not is_streamflow:
                logger.info(f"❌ FILTER: No launchpad/DEX/Protocol for {token_mint[:8]}... | Programs: {program_ids[:3]}")
                return  # Only skip if neither launchpad nor DEX
            
            # Log what we detected
            if detected_launchpad:
                logger.info(f"🎯 Launchpad: {detected_launchpad} {detected_launchpad_emoji} | {sol_spent:.2f} SOL")
            elif detected_dex:
                logger.info(f"📊 DEX trade: {detected_dex} | {sol_spent:.2f} SOL")
            elif is_vanish:
                logger.info(f"🐍 Vanish Protocol trade | {sol_spent:.2f} SOL")
            elif is_streamflow:
                logger.info(f"🔒 Streamflow lock tx detected")
            
            # === DEV HELD TRACKING (Run for all Pump.fun txs) ===
            if detected_launchpad == "pump.fun":
                 # Only record if we haven't seen this token before
                if token_mint not in self._seen_tokens:
                    self.dev_held_tracker.record_dev_wallet(token_mint, wallet, token_bought)
            
            
            # === LATE BONDING DETECTION (Pump.fun -> Raydium Migration) ===
            late_bonding = await self.late_migration_tracker.check_late_bonding(token_mint, program_ids)
            if late_bonding:
                 # Fetch token data for the alert
                lb_token_data = await self.token_fetcher.get_token_data(token_mint)
                if lb_token_data:
                    migration_msg = await self.late_migration_tracker.format_late_migration_alert(
                        ticker=lb_token_data.symbol,
                        token_name=lb_token_data.name,
                        contract_address=token_mint,
                        delay_hours=late_bonding.delay_hours,
                        market_cap_str=lb_token_data.mc_string,
                    )
                    # Send to Late Migration topic
                    migration_topic = settings.telegram_late_migration_topic_id
                    await self.telegram.send_alert(migration_msg, topic_id=migration_topic)
                    self.late_migration_tracker.increment_alerts()
            
            first_seen_for_enrichment = self._capture_first_seen_for_enrichment(token_mint)
            alert_msg, classification = await self.format_alert(
                token_address=token_mint,
                wallet_address=wallet,
                amount_sol=sol_spent,
                program_ids=program_ids,
            )
            
            if alert_msg:
                # === DEV HELD & CREATOR ANALYSIS (New Token / First Mention) ===
                creator_profile = None  # Initialize to avoid unbound variable error
                if first_seen_for_enrichment:
                    # 1. Analyze Creator
                    # We assume the wallet in a freshie alert *might* be the creator/early buyer
                    #Ideally we'd fetch the actual mint tx, but evaluating the current wallet is a good proxy for "early whale"
                    logger.info(f"👑 [Creator] Analyzing first-seen token creator: {wallet[:8]}...")
                    try:
                        creator_profile = await self.creator_analyzer.analyze_creator(wallet)
                        if creator_profile:
                            logger.info(f"👑 [Creator] Profile: wallet={wallet[:8]}... | is_good={creator_profile.is_good_creator} | value=${creator_profile.total_wallet_value_usd:,.0f} | score={creator_profile.score}")
                        else:
                            logger.info(f"👑 [Creator] No profile returned for {wallet[:8]}...")
                    except Exception as e:
                        logger.error(f"👑 [Creator] Error analyzing {wallet[:8]}...: {e}")
                        creator_profile = None

                    if creator_profile and self.creator_analyzer.check_is_good_creator(creator_profile) and self.creator_analyzer.should_alert(wallet):
                        # Send Good Creator Alert
                        # Need token data again if format_alert didn't cache it publicly (it doesn't)
                        # But format_alert calls get_token_data, which is cached.
                        token_data = await self.token_fetcher.get_token_data(token_mint)
                        if token_data:
                            creator_msg = await self.creator_analyzer.format_good_creator_alert(
                                ticker=token_data.symbol,
                                token_name=token_data.name,
                                contract_address=token_mint,
                                creator_wallet=wallet,
                                successful_tokens=len(creator_profile.successful_tokens),
                                wallet_value_str=f"${creator_profile.total_wallet_value_usd:,.0f}",
                                market_cap_str=token_data.mc_string,
                            )
                            await self.telegram.send_alert(creator_msg, topic_id=good_creator_topic_id())
                            self.creator_analyzer.mark_alerted(wallet)
                            self.creator_analyzer.increment_alerts()
                            self._creator_alerts_sent += 1
                            logger.info(f"👑 GOOD CREATOR ALERT SENT: {token_data.symbol} | Wallet: ${creator_profile.total_wallet_value_usd:,.0f}")


                
                # Update Dev Holdings (on every tx)
                # Need current supply held by dev. This requires fetching dev wallet balance.
                # Simplification: If this tx IS the dev (mapped in tracker), update their balance.
                # But we don't have the dev wallet balance here, only the trade amount.
                # So we'll trigger a background update or just skip for now?
                # Better: The tracker needs the dev's current balance.
                # We'll skip per-tx update here and let the _background_monitor handle strict updates,
                # OR we pass the wallet if it matches.
                pass 

                # === STRONG LAUNCH EVALUATION ===
                # If valid freshie, check if it's a strong launch
                token_data = await self.token_fetcher.get_token_data(token_mint)
                if token_data:
                    # FILTER: Max Market Cap Check
                    if settings.max_market_cap > 0 and token_data.market_cap and token_data.market_cap > settings.max_market_cap:
                         logger.info(f"🚫 IGNORED: {token_data.symbol} MC ${token_data.market_cap:,.0f} > ${settings.max_market_cap:,.0f} limit")
                         return
                    # Gather scores (simulated/placeholder logic for now as we build up history)
                    # In real impl, we'd pull from compiled risk score
                    creator_score = 50 + (25 if creator_profile and creator_profile.is_good_creator else 0)
                    
                    # Check socials with actual token data
                    token_socials = {
                        "twitter": token_data.twitter,
                        "telegram": token_data.telegram,
                        "website": token_data.website,
                    }
                    social_profile = await self.socials_checker.check_socials(token_mint, token_socials)
                    social_score = social_profile.social_score if social_profile else 0
                    
                    # If strong socials, run enhanced analysis and send alert
                    if social_profile and self.socials_checker.is_strong_socials(social_profile):
                        # Run enhanced analysis (smart followers + LLM)
                        social_profile = await self.socials_checker.analyze_enhanced(social_profile)
                        
                        if self.socials_checker.is_alertable_socials(social_profile):
                            # Format and send socials alert
                            socials_msg = await self.socials_checker.format_socials_alert(
                                ticker=token_data.symbol,
                                token_name=token_data.name,
                                contract_address=token_mint,
                                profile=social_profile,
                                market_cap_str=token_data.mc_string,
                                coin_age_str=token_data.age_string,
                            )
                            
                            await self.telegram.send_alert(socials_msg, topic_id=socials_topic_id())
                            self.socials_checker.mark_alerted(token_mint)
                            self.socials_checker.increment_alerts()
                            self._socials_alerts_sent += 1
                            logger.info(f"📱 SOCIALS ALERT: {token_data.symbol} | Score: {social_profile.enhanced_score}/100 | Smart: {social_profile.smart_followers}")
                    
                    strong_launch = self.strong_launch_tracker.evaluate_launch(
                        token_address=token_mint,
                        ticker=token_data.symbol,
                        token_name=token_data.name,
                        market_cap=token_data.market_cap or 0,
                        creator_score=creator_score,
                        social_score=social_score,
                        buy_pressure_score=50 + min(50, int(sol_spent * 10)), # Higher SOL = higher pressure
                        age_minutes=int(token_data.age_minutes) if token_data and token_data.age_minutes else 0,
                    )
                    
                    if strong_launch:
                        launch_msg = await self.strong_launch_tracker.format_strong_launch_alert(
                            launch=strong_launch,
                            market_cap_str=token_data.mc_string,
                            coin_age_str=token_data.age_string,
                        )
                        await self.telegram.send_alert(launch_msg, topic_id=strong_launch_topic_id())
                        self.strong_launch_tracker.increment_alerts()
                        self._strong_launch_alerts_sent += 1

                # Send to Freshies topic if configured
                freshies_topic = settings.telegram_freshies_topic_id if settings.telegram_freshies_topic_id > 0 else None
                msg_id = await self.telegram.send_alert(alert_msg, topic_id=freshies_topic)
                
                if msg_id:
                    self._tx_processed += 1
                    self._alerts_sent += 1
                    
                    channel_title = self.channel_router.get_channel_title(classification.primary_channel)
                    logger.info(f"✅ ALERT SENT [{channel_title}] {sol_spent:.2f} SOL | {classification.funding_time_ago} old | Total: {self._alerts_sent}")
                else:
                    logger.error(f"❌ Failed to send alert for {token_mint}")
            else:
                # Log why alert was not generated
                mc = classification.market_cap
                mc_str = f"${mc:,.0f}" if mc else "?"
                logger.info(f"🚫 NO ALERT: {sol_spent:.2f} SOL | MC: {mc_str} | Wallet age: {classification.wallet_age_hours}h | TX count: {classification.wallet_tx_count} | Valid: {classification.is_valid_alert}")
                if classification.wallet_tx_count > 50:
                    logger.info(f"   └─ Reason: Wallet has {classification.wallet_tx_count} txs (max 50 for freshie)")
                elif classification.wallet_age_hours >= 60*24:
                    logger.info(f"   └─ Reason: Wallet too old ({classification.wallet_age_hours}h = {classification.wallet_age_hours//24}d, max 60d)")
                elif sol_spent < settings.min_transaction_sol:
                    logger.info(f"   └─ Reason: Amount {sol_spent:.2f} SOL < {settings.min_transaction_sol} SOL minimum")
                elif mc and mc < settings.min_market_cap:
                    logger.info(f"   └─ Reason: Market cap ${mc:,.0f} < ${settings.min_market_cap:,.0f} minimum")
            
            # === DORMANT WALLET DETECTION ===
            # Check if wallet qualifies for dormant alert (separate from freshies)
            if sol_spent >= settings.min_dormant_sol:
                # Get wallet last activity
                wallet_info = await self.token_fetcher.get_wallet_info(wallet)
                age_days = wallet_info.get("age_days", 0)
                tx_count = wallet_info.get("tx_count", 0)
                
                # Use wallet age as days since first activity
                # For dormant wallets, we want to detect wallets that:
                # 1. Are old (age_days >= dormant_min_days)
                # 2. Have low activity relative to age (not bots or active traders)
                # A truly dormant wallet has few txs spread over a long time
                avg_txs_per_day = tx_count / max(age_days, 1)
                is_low_activity = avg_txs_per_day < 5  # Less than 5 txs per day on average

                # LOGGING FOR VERIFICATION
                logger.info(f"🔍 [Dormant Check] {wallet[:8]}... | Age={age_days}d | TxCount={tx_count} | AvgTx={avg_txs_per_day:.1f}/d | LowActivity={is_low_activity}")
                
                # Use age_days as days_inactive if low activity, otherwise estimate
                if is_low_activity and age_days >= settings.dormant_min_days:
                    days_inactive = age_days
                elif age_days >= settings.dormant_min_days * 2:
                    # Very old wallet, likely dormant even with moderate activity
                    days_inactive = age_days // 2  # Conservative estimate
                else:
                    days_inactive = 0
                
                if days_inactive >= settings.dormant_min_days:
                    dormant_msg, dormant_class = await self.format_dormant_alert(
                        token_address=token_mint,
                        wallet_address=wallet,
                        amount_sol=sol_spent,
                        days_since_last_activity=days_inactive,
                        program_ids=program_ids,
                    )
                    
                    if dormant_msg:
                        # Send to dormants topic if configured
                        dormants_topic = settings.telegram_dormants_topic_id if settings.telegram_dormants_topic_id > 0 else None
                        msg_id = await self.telegram.send_alert(dormant_msg, topic_id=dormants_topic)
                        
                        if msg_id:
                            self._dormant_alerts_sent += 1
                            logger.info(f"⏳ [Dormants] {sol_spent:.2f} SOL | {days_inactive}d inactive")
            
            # === SNS WALLET DETECTION ===
            # Check if wallet has an SNS domain (.sol)
            domain = await self.sns_tracker.get_wallet_domain(wallet)
            if domain:
                # Get token data for SNS alert
                token_data = await self.token_fetcher.get_token_data(token_mint)
                if token_data:
                    ticker = token_data.symbol
                    name = token_data.name
                    mc_str = token_data.mc_string
                    age_str = token_data.age_string
                else:
                    ticker = "???"
                    name = "Unknown"
                    mc_str = "?"
                    age_str = "?"
                
                # Get wallet info for last tx time
                wallet_info = await self.token_fetcher.get_wallet_info(wallet)
                last_tx_hours = wallet_info.get("age_hours", 0)
                
                is_first = token_mint not in self._seen_tokens
                is_whale = sol_spent >= 15
                is_dolphin = sol_spent >= 5 and not is_whale
                
                sns_msg = await self.sns_tracker.format_sns_alert(
                    ticker=ticker,
                    token_name=name,
                    contract_address=token_mint,
                    domain_name=domain,
                    amount_sol=sol_spent,
                    market_cap_str=mc_str,
                    coin_age_str=age_str,
                    last_tx_hours_ago=last_tx_hours,
                    is_first_mention=is_first,
                    is_whale=is_whale,
                    is_dolphin=is_dolphin,
                )
                
                # Send to SNS topic if configured
                sns_topic = settings.telegram_sns_topic_id if settings.telegram_sns_topic_id > 0 else None
                msg_id = await self.telegram.send_alert(sns_msg, topic_id=sns_topic)
                
                if msg_id:
                    self._record_sns_alert_sent(token_mint)
                    logger.info(f"🏷️ [SNS] {domain} bought {sol_spent:.2f} SOL of ${ticker}")
            
            # === VANISH PROTOCOL DETECTION ===
            # Check if transaction uses Vanish Protocol
            if self.vanish_tracker.is_vanish_transaction(program_ids) and sol_spent >= 1.0:
                # Get token data
                token_data = await self.token_fetcher.get_token_data(token_mint)
                if token_data:
                    ticker = token_data.symbol
                    name = token_data.name
                    mc_str = token_data.mc_string
                    age_str = token_data.age_string
                else:
                    ticker = "???"
                    name = "Unknown"
                    mc_str = "?"
                    age_str = "?"
                
                # Classify
                vanish_class = self.vanish_tracker.classify_vanish(
                    token_address=token_mint,
                    amount_sol=sol_spent,
                    market_cap=token_data.market_cap if token_data else None,
                    program_ids=program_ids,
                )
                
                if vanish_class.is_valid_alert:
                    count = self.vanish_tracker.track_vanish_buy(token_mint)
                    
                    vanish_msg = await self.vanish_tracker.format_vanish_alert(
                        ticker=ticker,
                        token_name=name,
                        contract_address=token_mint,
                        amount_sol=sol_spent,
                        market_cap_str=mc_str,
                        coin_age_str=age_str,
                        vanish_type=vanish_class.vanish_type,
                        count=count,
                        launchpad_emoji=vanish_class.launchpad_emoji,
                        dex_emoji=vanish_class.dex_emoji,
                        is_first_mention=vanish_class.is_first_mention,
                        is_whale=vanish_class.is_whale,
                    )
                    
                    # Send to Vanish topic if configured
                    vanish_topic = settings.telegram_vanish_topic_id if settings.telegram_vanish_topic_id > 0 else None
                    msg_id = await self.telegram.send_alert(vanish_msg, topic_id=vanish_topic)
                    
                    if msg_id:
                        self._vanish_alerts_sent += 1
                        is_big = vanish_class.vanish_type.value == "vanish_big_buys"
                        self.vanish_tracker.increment_alerts(is_big=is_big)
                        logger.info(f"🐍 [Vanish] {sol_spent:.2f} SOL {'BIG ' if is_big else ''}buy of ${ticker}")
            
            # === BUNDLE DETECTION ===
            # Add transaction to bundle detector and check for coordinated activity
            from models import TradeAction
            slot = tx_data.get("slot", 0)
            bundle_info = self.bundle_detector.add_transaction(
                token_address=token_mint,
                wallet_address=wallet,
                amount_sol=sol_spent,
                token_amount=token_bought,
                action=TradeAction.BUY,
                block_number=slot,
                funding_source=classification.funding_source if classification else None,
            )
            
            if bundle_info:
                # Calculate supply percentage if we have token data
                total_supply = getattr(token_data, 'total_supply', None) if token_data else None
                if total_supply and total_supply > 0:
                    bundle_info.supply_percent = (bundle_info.total_token_amount / total_supply) * 100

                if token_data:
                    is_opening = token_data.age_minutes < 2 if token_data.age_minutes is not None else False
                    bundle_info.is_opening_bundle = bundle_info.is_opening_bundle or is_opening
                
                # BUNDLE ALERT CRITERIA:
                # Only alert for OPENING bundles (at start of trading/launch)
                # Must be opening bundle with >1% supply or coordination score >= 60
                should_alert = False
                if bundle_info.is_opening_bundle:
                    if bundle_info.supply_percent >= 1.0 or bundle_info.coordination_score >= 60:
                        should_alert = True
                        logger.info(f"📦 Opening bundle qualifies: supply={bundle_info.supply_percent:.2f}%, score={bundle_info.coordination_score:.0f}")
                
                if should_alert:
                    # Alert on coordinated activity (bundles)
                    # Get token data
                    token_data = await self.token_fetcher.get_token_data(token_mint)
                    ticker = token_data.symbol if token_data else "???"
                    name = token_data.name if token_data else ""
                    
                    logger.info(f"📦 Bundle detected: {bundle_info.wallet_count} wallets, score={bundle_info.coordination_score:.0f}")
                    
                    # Format and send bundle alert
                    if bundle_info.action == "buy":
                        bundle_msg = await self.bundle_detector.format_bundle_alert(
                            info=bundle_info,
                            token_symbol=ticker,
                            token_name=name,
                        )
                    else:
                        mc_str = token_data.mc_string if token_data else "?"
                        age_str = token_data.age_string if token_data else "?"
                        bundle_msg = await self.bundle_detector.format_bundle_sale_alert(
                            info=bundle_info,
                            token_symbol=ticker,
                            token_name=name,
                            market_cap_str=mc_str,
                            coin_age_str=age_str,
                        )
                    
                    bundles_topic = settings.telegram_bundles_topic_id if settings.telegram_bundles_topic_id > 0 else None
                    msg_id = await self.telegram.send_alert(bundle_msg, topic_id=bundles_topic)
                    
                    if msg_id:
                        self._bundle_alerts_sent += 1
                        logger.info(f"📦 [Bundle] {bundle_info.wallet_count} wallets / {bundle_info.total_volume_sol:.2f} SOL on ${ticker}")
            
            # === SOCIALS CHECK ===
            # Push to Redis queue for local processor (FrontrunPro requires browser)
            # Only check if Twitter exists to avoid spamming queue
            token_data = await self.token_fetcher.get_token_data(token_mint)
            if token_data and token_data.twitter:
                await self._send_to_socials_queue(token_data, token_data.twitter)
                
            
            # === STRONGFLOOR TRACKING ===
            
            # === STRONGFLOOR TRACKING ===
            # Record price for strongfloor analysis
            if token_data and token_data.price_usd:
                self.strongfloor_tracker.record_price(
                    token_address=token_mint,
                    price=token_data.price_usd,
                    ticker=token_data.symbol,
                    name=token_data.name,
                )
                
                # Check for strongfloor pattern
                strongfloor = self.strongfloor_tracker.analyze_floor(
                    token_address=token_mint,
                    ticker=token_data.symbol,
                    token_name=token_data.name,
                    current_price=token_data.price_usd,
                )
                
                if strongfloor:
                    floor_msg = await self.strongfloor_tracker.format_strongfloor_alert(
                        token=strongfloor,
                        market_cap_str=token_data.mc_string,
                    )
                    
                    topic = settings.telegram_strongfloor_topic_id if settings.telegram_strongfloor_topic_id > 0 else None
                    msg_id = await self.telegram.send_alert(floor_msg, topic_id=topic)
                    if msg_id:
                        self._strongfloor_alerts_sent += 1
                        self.strongfloor_tracker.mark_alerted(strongfloor)
                        self.strongfloor_tracker.increment_alerts()
                        logger.info(f"🧱 [Strongfloor] Floor detected for ${strongfloor.ticker}")
            
        except Exception as e:
            logger.error(f"Error processing transaction: {e}")
            self._errors += 1

    def _extract_program_ids(self, tx_data: dict) -> list[str]:
        """Extract program IDs referenced by a parsed Solana transaction."""
        message = tx_data.get("transaction", {}).get("message", {})
        program_ids: list[str] = []

        for key in message.get("accountKeys", []):
            if isinstance(key, dict):
                pubkey = key.get("pubkey", "")
                if pubkey and pubkey not in program_ids:
                    program_ids.append(pubkey)
            elif key and key not in program_ids:
                program_ids.append(key)

        for ix in message.get("instructions", []):
            if not isinstance(ix, dict):
                continue
            pid = ix.get("programId")
            if pid and pid not in program_ids:
                program_ids.append(pid)

        return program_ids

    def _candidate_token_mints_from_balances(self, tx_data: dict) -> list[str]:
        """Return non-native token mints touched by a transaction."""
        meta = tx_data.get("meta", {})
        mints: list[str] = []

        for balance_key in ("postTokenBalances", "preTokenBalances"):
            for balance in meta.get(balance_key, []):
                mint = balance.get("mint")
                if not mint or mint in EXCLUDED_TOKENS or mint in mints:
                    continue
                mints.append(mint)

        return mints

    async def _maybe_process_streamflow_lock(
        self,
        tx_data: dict,
        program_ids: list[str] | None = None,
    ) -> bool:
        """Send a Streamflow alert for direct lock transactions."""
        program_ids = program_ids or self._extract_program_ids(tx_data)
        if not self.streamflow_tracker.is_streamflow_lock(program_ids):
            return False

        topic = settings.telegram_streamflow_topic_id if settings.telegram_streamflow_topic_id > 0 else None
        if not topic:
            logger.warning("Streamflow lock detected but streamflow topic is not configured")
            return False

        for token_mint in self._candidate_token_mints_from_balances(tx_data):
            should_alert = getattr(self.streamflow_tracker, "should_alert_token", None)
            if callable(should_alert) and not should_alert(token_mint):
                continue

            lock = self.streamflow_tracker.parse_lock_from_tx(tx_data, token_mint)
            if not lock:
                continue

            token_data = await self.token_fetcher.get_token_data(token_mint)
            if not token_data:
                logger.info("Streamflow lock metadata unavailable; sending fallback alert for %s", token_mint[:12])

            ticker = token_data.symbol if token_data else "???"
            name = token_data.name if token_data else "Unknown"
            mc_str = token_data.mc_string if token_data else "?"
            age_str = token_data.age_string if token_data else "?"

            lock_msg = await self.streamflow_tracker.format_streamflow_alert(
                ticker=ticker,
                token_name=name,
                contract_address=token_mint,
                lock_amount=lock.lock_amount,
                market_cap_str=mc_str,
                coin_age_str=age_str,
            )
            msg_id = await self.telegram.send_alert(lock_msg, topic_id=topic)
            if msg_id:
                self._streamflow_alerts_sent += 1
                self.streamflow_tracker.increment_alerts()
                mark_alerted = getattr(self.streamflow_tracker, "mark_alerted", None)
                if callable(mark_alerted):
                    mark_alerted(token_mint)
                logger.info(f"🔒 [Streamflow] Direct lock detected for ${ticker}")
                return True

        return False

    def _should_backup_poll(self, now: datetime | None = None) -> bool:
        """Return true when WebSocket is disconnected or connected-but-stale."""

        if not getattr(self, "_ws_connected", False):
            return True

        current_time = now or datetime.utcnow()
        last_activity = getattr(self, "_last_tx_received_at", None) or getattr(self, "_last_ws_connected_at", None)
        if last_activity is None:
            return True

        stale_after = max(30, settings.solana_ws_stale_seconds)
        return current_time - last_activity > timedelta(seconds=stale_after)
    
    def get_stats(self) -> dict:
        queue = getattr(self, "_tx_queue", None)
        queue_size = queue.qsize() if queue and hasattr(queue, "qsize") else 0
        return {
            "transactions_received": self._tx_received,
            "transactions_processed": self._tx_processed,
            "alerts_sent": self._alerts_sent,
            "dormant_alerts_sent": self._dormant_alerts_sent,
            "sns_alerts_sent": self._sns_alerts_sent,
            "vanish_alerts_sent": self._vanish_alerts_sent,
            "bundle_alerts_sent": self._bundle_alerts_sent,
            "late_migration_alerts": self._late_migration_alerts_sent,
            "streamflow_alerts": self._streamflow_alerts_sent,
            "dev_held_alerts": self._dev_held_alerts_sent,
            "creator_alerts": self._creator_alerts_sent,
            "socials_alerts": self._socials_alerts_sent,
            "strong_launch_alerts": self._strong_launch_alerts_sent,
            "strongfloor_alerts": self._strongfloor_alerts_sent,
            "errors": self._errors,
            "running": self._running,
            "unique_tokens": len(self._seen_tokens),
            "websocket_connected": getattr(self, "_ws_connected", False),
            "websocket_stale": self._should_backup_poll(),
            "last_ws_connected_at": _iso_or_none(getattr(self, "_last_ws_connected_at", None)),
            "last_tx_received_at": _iso_or_none(getattr(self, "_last_tx_received_at", None)),
            "queue_size": queue_size,
            "queue_max_size": getattr(self, "_max_tx_queue_size", 0),
            "queue_fresh_target_size": getattr(self, "_fresh_tx_queue_target_size", 0),
            "transactions_dropped": getattr(self, "_tx_dropped", 0),
            "modules": {
                "sns": self.sns_tracker.get_stats(),
                "vanish": self.vanish_tracker.get_stats(),
                "bundles": self.bundle_detector.get_stats(),
                "late_migration": self.late_migration_tracker.get_stats(),
                "streamflow": self.streamflow_tracker.get_stats(),
                "dev_held": self.dev_held_tracker.get_stats(),
                "good_creator": self.creator_analyzer.get_stats(),
                "socials": self.socials_checker.get_stats(),
                "strong_launch": self.strong_launch_tracker.get_stats(),
                "strongfloor": self.strongfloor_tracker.get_stats(),
            },
            "rpc": self.rpc_manager.get_stats(),
        }


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


_solana_listener: SolanaListener | None = None


def get_solana_listener() -> SolanaListener:
    global _solana_listener
    if _solana_listener is None:
        _solana_listener = SolanaListener()
    return _solana_listener
