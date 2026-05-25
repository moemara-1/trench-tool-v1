"""
Pattern Detection Service

Tracks token behavior patterns and generates alerts for:
- Price Volatility (50%+ drop for 5M+ MC)
- Volume Spike (volume after 30min inactivity)
- Bundle Out (90%+ bundle wallets exited)
- Dormants Inflow/Pre-Migration
- Freshies Inflow/Spike variants
- Freshies Selling
"""

import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from config import settings
from services.api_clients import get_token_fetcher

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Pattern categories."""
    PRICE_VOLATILITY = "PRICE VOLATILITY"
    VOLUME_SPIKE = "VOLUME SPIKE"
    BUNDLE_OUT = "BUNDLE OUT"
    DORMANTS_INFLOW = "DORMANTS INFLOW"
    PRE_MIGRATION_DORMANTS = "PRE-MIGRATION DORMANTS"
    FRESHIES_INFLOW = "FRESHIES INFLOW"
    TG_FRESHIES_INFLOW = "TG FRESHIES INFLOW"
    OLD_FRESHIES_INFLOW = "OLD FRESHIES INFLOW"
    LOW_MC_FRESHIES_INFLOW = "LOW MC FRESHIES INFLOW"
    FRESHIES_SPIKE = "FRESHIES SPIKE"
    TG_FRESHIES_SPIKE = "TG FRESHIES SPIKE"
    OLD_FRESHIES_SPIKE = "OLD FRESHIES SPIKE"
    LOW_MC_FRESHIES_SPIKE = "LOW MC FRESHIES SPIKE"
    FRESHIES_SELLING_GREEN = "FRESHIES SELLING"
    FRESHIES_SELLING_RED = "FRESHIES SELLING"


@dataclass
class BuyEvent:
    """Recorded buy event."""
    timestamp: datetime
    wallet: str
    sol_amount: float
    router: Optional[str] = None
    funding_source: Optional[str] = None
    is_dormant: bool = False
    is_fresh: bool = False
    is_old_fresh: bool = False  # Funded 24h+ ago
    is_tg_router: bool = False


@dataclass
class SellEvent:
    """Recorded sell event."""
    timestamp: datetime
    wallet: str
    is_full_sell: bool = True
    is_fresh: bool = False


@dataclass
class TokenPatternState:
    """Tracks pattern-related state for a token."""
    token_address: str
    symbol: str = "???"
    name: str = "Unknown"
    market_cap: Optional[float] = None
    age_minutes: int = 0
    launchpad: str = ""
    launchpad_emoji: str = ""
    is_migrated: bool = False
    
    # Event history
    fresh_buys: List[BuyEvent] = field(default_factory=list)
    dormant_buys: List[BuyEvent] = field(default_factory=list)
    all_buys: List[BuyEvent] = field(default_factory=list)
    fresh_sells: List[SellEvent] = field(default_factory=list)
    
    # Price tracking
    last_price: Optional[float] = None
    price_24h_ago: Optional[float] = None
    last_buy_time: Optional[datetime] = None
    
    # Bundle tracking
    bundle_wallets: Set[str] = field(default_factory=set)
    bundle_exits: Set[str] = field(default_factory=set)
    
    # Pattern trigger counts
    pattern_triggers: Dict[PatternType, int] = field(default_factory=lambda: defaultdict(int))
    last_pattern_alert: Dict[PatternType, datetime] = field(default_factory=dict)


# Pattern thresholds
THRESHOLDS = {
    "price_volatility_drop_pct": 50,
    "price_volatility_min_mc": 5_000_000,
    "volume_spike_inactivity_mins": 30,
    "bundle_out_exit_pct": 90,
    "dormants_inflow_count": 5,
    "dormants_inflow_window_hours": 2,
    "pre_migration_dormants_count": 3,
    "freshies_inflow_count": 5,
    "freshies_inflow_window_mins": 5,
    "tg_freshies_inflow_count": 15,
    "tg_freshies_inflow_window_hours": 2,
    "old_freshies_inflow_count": 15,
    "old_freshies_inflow_window_hours": 2,
    "low_mc_freshies_inflow_count": 15,
    "low_mc_freshies_inflow_window_hours": 2,
    "low_mc_threshold": 500_000,
    "freshies_spike_count": 5,
    "freshies_spike_window_mins": 5,
    "pattern_cooldown_mins": 10,  # Don't re-alert same pattern within this time
}

# Router emojis
ROUTER_EMOJIS = {
    "banana": "🍌",
    "maestro": "Ⓜ️",
    "trojan": "🔱",
    "bloom": "🌸",
    "mintech": "📱",
    "bonk": "🐕",
    "axiom": "🔳",
    "padre": "🏮",
    "telemetry": "🐶",
    "nova": "♋️",
    "photon": "🔆",
}

# Launchpad emojis
LAUNCHPAD_EMOJIS = {
    "pump.fun": "💊",
    "moonshot": "🌕",
    "bonk": "🐕",
    "raydium": "🔮",
    "sugar": "🍭",
}


class PatternDetector:
    """Detects and alerts on token behavior patterns."""
    
    def __init__(self):
        self._tokens: Dict[str, TokenPatternState] = {}
        self._lock = asyncio.Lock()
        # Import telegram bot lazily to avoid circular imports
        self._telegram = None
    
    def _get_telegram(self):
        if self._telegram is None:
            from alerts.telegram_bot import get_telegram_bot
            self._telegram = get_telegram_bot()
        return self._telegram

    def _destination_topic_id(self) -> Optional[int]:
        """Return the configured Patterns topic, or None when disabled."""
        topic_id = getattr(settings, "telegram_patterns_topic_id", 0)
        if topic_id and topic_id > 0:
            return topic_id
        return None
    
    def _get_or_create_token(self, token_address: str) -> TokenPatternState:
        """Get or create token state."""
        if token_address not in self._tokens:
            self._tokens[token_address] = TokenPatternState(token_address=token_address)
        return self._tokens[token_address]
    
    def update_token_info(
        self,
        token_address: str,
        symbol: str = None,
        name: str = None,
        market_cap: float = None,
        age_minutes: int = None,
        launchpad: str = None,
        launchpad_emoji: str = None,
        is_migrated: bool = None,
        current_price: float = None,
    ):
        """Update token metadata."""
        state = self._get_or_create_token(token_address)
        if symbol:
            state.symbol = symbol
        if name:
            state.name = name
        if market_cap is not None:
            state.market_cap = market_cap
        if age_minutes is not None:
            state.age_minutes = age_minutes
        if launchpad:
            state.launchpad = launchpad
        if launchpad_emoji:
            state.launchpad_emoji = launchpad_emoji
        if is_migrated is not None:
            state.is_migrated = is_migrated
        if current_price is not None:
            # Track price for volatility detection
            if state.last_price is not None:
                # Check for price drop
                drop_pct = ((state.last_price - current_price) / state.last_price) * 100
                if drop_pct >= THRESHOLDS["price_volatility_drop_pct"]:
                    if state.market_cap and state.market_cap >= THRESHOLDS["price_volatility_min_mc"]:
                        asyncio.create_task(self._trigger_pattern(
                            token_address, 
                            PatternType.PRICE_VOLATILITY,
                            extra_data={"drop_pct": drop_pct}
                        ))
            state.last_price = current_price
    
    async def record_buy(
        self,
        token_address: str,
        wallet: str,
        sol_amount: float,
        is_fresh: bool = False,
        is_dormant: bool = False,
        is_old_fresh: bool = False,
        router: str = None,
        funding_source: str = None,
    ):
        """Record a buy event and check for patterns."""
        state = self._get_or_create_token(token_address)
        now = datetime.utcnow()
        
        is_tg_router = router in ROUTER_EMOJIS if router else False
        
        event = BuyEvent(
            timestamp=now,
            wallet=wallet,
            sol_amount=sol_amount,
            router=router,
            funding_source=funding_source,
            is_dormant=is_dormant,
            is_fresh=is_fresh,
            is_old_fresh=is_old_fresh,
            is_tg_router=is_tg_router,
        )
        
        state.all_buys.append(event)
        state.last_buy_time = now
        
        if is_fresh:
            state.fresh_buys.append(event)
        if is_dormant:
            state.dormant_buys.append(event)
        
        # Prune old events (keep last 4 hours)
        cutoff = now - timedelta(hours=4)
        state.fresh_buys = [e for e in state.fresh_buys if e.timestamp > cutoff]
        state.dormant_buys = [e for e in state.dormant_buys if e.timestamp > cutoff]
        state.all_buys = [e for e in state.all_buys if e.timestamp > cutoff]
        
        # Check patterns
        await self._check_patterns(token_address)
    
    async def record_sell(
        self,
        token_address: str,
        wallet: str,
        is_full_sell: bool = True,
        is_fresh: bool = False,
    ):
        """Record a sell event."""
        state = self._get_or_create_token(token_address)
        now = datetime.utcnow()
        
        event = SellEvent(
            timestamp=now,
            wallet=wallet,
            is_full_sell=is_full_sell,
            is_fresh=is_fresh,
        )
        
        state.fresh_sells.append(event)
        
        # Check bundle exits
        if wallet in state.bundle_wallets:
            state.bundle_exits.add(wallet)
            await self._check_bundle_out(token_address)
        
        # Prune old events
        cutoff = now - timedelta(hours=2)
        state.fresh_sells = [e for e in state.fresh_sells if e.timestamp > cutoff]
    
    def register_bundle_wallets(self, token_address: str, wallets: Set[str]):
        """Register bundle wallets for tracking exits."""
        state = self._get_or_create_token(token_address)
        state.bundle_wallets.update(wallets)
    
    async def _check_patterns(self, token_address: str):
        """Check all pattern conditions for a token."""
        state = self._tokens.get(token_address)
        if not state:
            return
        
        now = datetime.utcnow()
        
        # === DORMANTS INFLOW ===
        # 5 dormant wallets buy in 2 hours
        window = now - timedelta(hours=THRESHOLDS["dormants_inflow_window_hours"])
        recent_dormants = [e for e in state.dormant_buys if e.timestamp > window]
        unique_dormant_wallets = set(e.wallet for e in recent_dormants)
        
        if len(unique_dormant_wallets) >= THRESHOLDS["dormants_inflow_count"]:
            await self._trigger_pattern(token_address, PatternType.DORMANTS_INFLOW)
        
        # === PRE-MIGRATION DORMANTS ===
        # 3 dormants before migration (pump.fun/moonshot only)
        if not state.is_migrated and state.launchpad in ["pump.fun", "moonshot"]:
            if len(unique_dormant_wallets) >= THRESHOLDS["pre_migration_dormants_count"]:
                await self._trigger_pattern(token_address, PatternType.PRE_MIGRATION_DORMANTS)
        
        # === FRESHIES INFLOW / SPIKE ===
        # 5 fresh wallets in 5 minutes
        spike_window = now - timedelta(minutes=THRESHOLDS["freshies_spike_window_mins"])
        recent_fresh = [e for e in state.fresh_buys if e.timestamp > spike_window]
        unique_fresh_wallets = set(e.wallet for e in recent_fresh)
        
        if len(unique_fresh_wallets) >= THRESHOLDS["freshies_spike_count"]:
            # Check sub-types
            tg_fresh = [e for e in recent_fresh if e.is_tg_router]
            old_fresh = [e for e in recent_fresh if e.is_old_fresh]
            
            if len(set(e.wallet for e in tg_fresh)) >= THRESHOLDS["freshies_spike_count"]:
                await self._trigger_pattern(token_address, PatternType.TG_FRESHIES_SPIKE, extra_data={"events": tg_fresh})
            elif len(set(e.wallet for e in old_fresh)) >= THRESHOLDS["freshies_spike_count"]:
                await self._trigger_pattern(token_address, PatternType.OLD_FRESHIES_SPIKE, extra_data={"events": old_fresh})
            elif state.market_cap and state.market_cap <= THRESHOLDS["low_mc_threshold"]:
                await self._trigger_pattern(token_address, PatternType.LOW_MC_FRESHIES_SPIKE, extra_data={"events": recent_fresh})
            else:
                await self._trigger_pattern(token_address, PatternType.FRESHIES_SPIKE, extra_data={"events": recent_fresh})
        
        # === FRESHIES INFLOW (longer window) ===
        inflow_window = now - timedelta(hours=THRESHOLDS["tg_freshies_inflow_window_hours"])
        inflow_fresh = [e for e in state.fresh_buys if e.timestamp > inflow_window]
        unique_inflow_wallets = set(e.wallet for e in inflow_fresh)
        
        if len(unique_inflow_wallets) >= THRESHOLDS["tg_freshies_inflow_count"]:
            tg_inflow = [e for e in inflow_fresh if e.is_tg_router]
            old_inflow = [e for e in inflow_fresh if e.is_old_fresh]
            
            if len(set(e.wallet for e in tg_inflow)) >= THRESHOLDS["tg_freshies_inflow_count"]:
                await self._trigger_pattern(token_address, PatternType.TG_FRESHIES_INFLOW, extra_data={"events": tg_inflow})
            elif len(set(e.wallet for e in old_inflow)) >= THRESHOLDS["old_freshies_inflow_count"]:
                await self._trigger_pattern(token_address, PatternType.OLD_FRESHIES_INFLOW, extra_data={"events": old_inflow})
            elif state.market_cap and state.market_cap <= THRESHOLDS["low_mc_threshold"]:
                await self._trigger_pattern(token_address, PatternType.LOW_MC_FRESHIES_INFLOW, extra_data={"events": inflow_fresh})
        
        # === VOLUME SPIKE ===
        # Check if there was 30+ min inactivity followed by buy
        if state.last_buy_time and len(state.all_buys) >= 2:
            prev_buy = state.all_buys[-2] if len(state.all_buys) >= 2 else None
            if prev_buy:
                gap_mins = (now - prev_buy.timestamp).total_seconds() / 60
                if gap_mins >= THRESHOLDS["volume_spike_inactivity_mins"]:
                    if state.launchpad in ["pump.fun", "moonshot"]:
                        await self._trigger_pattern(token_address, PatternType.VOLUME_SPIKE)
    
    async def _check_bundle_out(self, token_address: str):
        """Check if 90%+ of bundle wallets have exited."""
        state = self._tokens.get(token_address)
        if not state or not state.bundle_wallets:
            return
        
        exit_pct = (len(state.bundle_exits) / len(state.bundle_wallets)) * 100
        if exit_pct >= THRESHOLDS["bundle_out_exit_pct"]:
            await self._trigger_pattern(token_address, PatternType.BUNDLE_OUT)
    
    async def _trigger_pattern(
        self,
        token_address: str,
        pattern_type: PatternType,
        extra_data: dict = None,
    ):
        """Trigger a pattern alert."""
        state = self._tokens.get(token_address)
        if not state:
            return
        
        now = datetime.utcnow()
        
        # Check cooldown
        cooldown = timedelta(minutes=THRESHOLDS["pattern_cooldown_mins"])
        last_alert = state.last_pattern_alert.get(pattern_type)
        if last_alert and (now - last_alert) < cooldown:
            return  # Still in cooldown
        
        # Update trigger count and last alert time
        state.pattern_triggers[pattern_type] += 1
        state.last_pattern_alert[pattern_type] = now
        trigger_count = state.pattern_triggers[pattern_type]
        
        # Format alert (async to fetch pair address for Axiom)
        alert = await self._format_pattern_alert(state, pattern_type, trigger_count, extra_data)
        
        # Send to Telegram only when a producer-backed patterns topic is configured.
        # Sending without a topic lands in Telegram's General topic, which this group uses as Feedback.
        topic_id = self._destination_topic_id()
        if not topic_id:
            logger.info(
                "Pattern alert suppressed because the patterns topic is disabled: %s",
                state.symbol,
            )
            return

        await self._get_telegram().send_alert(alert, topic_id=topic_id)
        
        logger.info(f"🧪 Pattern triggered: {pattern_type.value} for {state.symbol}")
    
    async def _format_pattern_alert(
        self,
        state: TokenPatternState,
        pattern_type: PatternType,
        trigger_count: int,
        extra_data: dict = None,
    ) -> str:
        """Format BBB-style pattern alert matching exact specifications."""
        
        extra_data = extra_data or {}
        lines = []
        
        # Get common values
        launchpad_emoji = state.launchpad_emoji or LAUNCHPAD_EMOJIS.get(state.launchpad.lower() if state.launchpad else "", "")
        mc_str = self._format_number(state.market_cap) if state.market_cap else "?"
        age_str = self._format_age(state.age_minutes)
        is_first_mention = trigger_count == 1
        first_mention_star = "⭐ " if is_first_mention else ""
        
        # Pattern-specific formatting
        if pattern_type == PatternType.PRICE_VOLATILITY:
            # Format: ⭐ PRICE VOLATILITY 61.50% 📉
            drop_pct = extra_data.get("drop_pct", 50)
            lines.append(f"{first_mention_star}PRICE VOLATILITY {drop_pct:.2f}% 📉")
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
            
        elif pattern_type == PatternType.VOLUME_SPIKE:
            # Format: VOLUME SPIKE📈 💥 with launchpad emoji
            lines.append(f"VOLUME SPIKE📈 💥")
            lines.append(f"{state.name} ✓ ${state.symbol} {launchpad_emoji} {mc_str} {age_str}")
            
        elif pattern_type == PatternType.BUNDLE_OUT:
            # Format: ⭐ BUNDLE OUT 📦 🌕
            lines.append(f"{first_mention_star}BUNDLE OUT 📦 {launchpad_emoji}")
            lines.append(f"${state.symbol} {state.name}")
            
        elif pattern_type == PatternType.DORMANTS_INFLOW:
            # Format: [N] DORMANTS INFLOW ⏳ 🌊
            lines.append(f"[{trigger_count}] DORMANTS INFLOW ⏳ 🌊")
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
            
        elif pattern_type == PatternType.PRE_MIGRATION_DORMANTS:
            # Format: [N] PRE-MIGRATION DORMANTS 💊 🌊
            lines.append(f"[{trigger_count}] PRE-MIGRATION DORMANTS {launchpad_emoji} 🌊")
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
            
        elif pattern_type in [PatternType.FRESHIES_INFLOW, PatternType.TG_FRESHIES_INFLOW, 
                              PatternType.OLD_FRESHIES_INFLOW, PatternType.LOW_MC_FRESHIES_INFLOW]:
            # Freshies Inflow patterns - Line 1: Pattern info
            events = extra_data.get("events", [])
            
            # Get router emoji for TG patterns
            router_emoji = ""
            if pattern_type == PatternType.TG_FRESHIES_INFLOW and events:
                routers = [e.router for e in events if e.router]
                if routers:
                    most_common_router = max(set(routers), key=routers.count)
                    router_emoji = ROUTER_EMOJIS.get(most_common_router.lower(), "")
            
            lines.append(f"{first_mention_star}{pattern_type.value} 👶 🌊")
            
            # Line 2: BBB tracker - Count | Funding | Avg SOL
            if events:
                unique_wallets = len(set(e.wallet for e in events))
                funding_sources = [e.funding_source for e in events if e.funding_source]
                most_common_funding = max(set(funding_sources), key=funding_sources.count) if funding_sources else "?"
                avg_sol = sum(e.sol_amount for e in events) / len(events) if events else 0
                lines.append(f"{unique_wallets} | {most_common_funding} ⚫ | {avg_sol:.2f}")
            
            # Line 3: Token info
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
            
        elif pattern_type in [PatternType.FRESHIES_SPIKE, PatternType.TG_FRESHIES_SPIKE,
                              PatternType.OLD_FRESHIES_SPIKE, PatternType.LOW_MC_FRESHIES_SPIKE]:
            # Freshies Spike patterns - same structure as inflow
            events = extra_data.get("events", [])
            
            # Get router emoji for TG patterns
            router_emoji = ""
            if pattern_type == PatternType.TG_FRESHIES_SPIKE and events:
                routers = [e.router for e in events if e.router]
                if routers:
                    most_common_router = max(set(routers), key=routers.count)
                    router_emoji = ROUTER_EMOJIS.get(most_common_router.lower(), "")
            
            lines.append(f"[{trigger_count}] {pattern_type.value} 👶 💥")
            
            # Line 2: BBB tracker
            if events:
                unique_wallets = len(set(e.wallet for e in events))
                funding_sources = [e.funding_source for e in events if e.funding_source]
                most_common_funding = max(set(funding_sources), key=funding_sources.count) if funding_sources else "?"
                avg_sol = sum(e.sol_amount for e in events) / len(events) if events else 0
                lines.append(f"{unique_wallets} | {most_common_funding} ⚫ | {avg_sol:.2f}")
            
            # Line 3: Token info
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
            
        elif pattern_type in [PatternType.FRESHIES_SELLING_GREEN, PatternType.FRESHIES_SELLING_RED]:
            # Freshies Selling patterns
            sell_emoji = "🟢" if pattern_type == PatternType.FRESHIES_SELLING_GREEN else "🔴"
            lines.append(f"[{trigger_count}] FRESHIES SELLING 👶 {sell_emoji}")
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
        
        else:
            # Generic fallback
            lines.append(f"[{trigger_count}] {pattern_type.value}")
            lines.append(f"${state.symbol} {state.name}  {mc_str} | {age_str}")
        
        # Add contract address
        lines.append(f"<code>{state.token_address}</code>")
        
        # Add socials if available (for Volume Spike and Freshies patterns)
        socials = extra_data.get("socials", {})
        if socials:
            social_links = []
            if socials.get("telegram"):
                social_links.append(f"<a href='{socials['telegram']}'>Telegram</a>")
            if socials.get("twitter"):
                social_links.append(f"<a href='{socials['twitter']}'>Twitter</a>")
            if socials.get("website"):
                social_links.append(f"<a href='{socials['website']}'>Website</a>")
            if social_links:
                lines.append(" | ".join(social_links))
        
        # Add trading links
        trading_links = await self._format_trading_links_async(state.token_address)
        lines.append(trading_links)
        
        return "\n".join(lines)
    
    def _format_number(self, num: float) -> str:
        """Format number with K/M/B suffix."""
        if num is None:
            return "?"
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.1f}B"
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        if num >= 1_000:
            return f"{num/1_000:.1f}K"
        return f"{num:.0f}"
    
    def _format_age(self, minutes: int) -> str:
        """Format age in minutes to human readable."""
        if minutes < 60:
            return f"{minutes}m"
        if minutes < 1440:
            return f"{minutes // 60}h"
        return f"{minutes // 1440}d"
    
    async def _format_trading_links_async(self, token_address: str) -> str:
        """Format trading bot quick links with pair address for Axiom."""
        # Try to get pair address for Axiom
        pair_address = await get_token_fetcher().get_pair_address(token_address)
        if not pair_address:
            pair_address = token_address
        
        links = [
            f"<a href='https://photon-sol.tinyastro.io/en/lp/{token_address}'>PH</a>",
            f"<a href='https://axiom.trade/meme/{pair_address}?chain=sol'>AX</a>",
            f"<a href='https://t.me/paris_trojanbot?start={token_address}'>TJ</a>",
            f"<a href='https://t.me/BananaGunSolana_bot?start={token_address}'>BA</a>",
            f"<a href='https://trade.padre.gg/trade/solana/{token_address}'>PR</a>",
            f"<a href='https://t.me/BloomSolana_bot?start={token_address}'>BL</a>",
            f"<a href='https://t.me/MaestroSniperBot?start={token_address}'>MA</a>",
            f"<a href='https://t.me/MaestroProBot?start={token_address}'>MT</a>",
            f"<a href='https://neo.bullx.io/terminal?chainId=1399811149&address={token_address}'>NE</a>",
            f"<a href='https://dexscreener.com/solana/{token_address}'>DS</a>",
            f"<a href='https://pump.fun/{token_address}'>PF</a>",
        ]
        return " | ".join(links)
    



# Singleton instance
_pattern_detector: Optional[PatternDetector] = None


def get_pattern_detector() -> PatternDetector:
    """Get singleton pattern detector."""
    global _pattern_detector
    if _pattern_detector is None:
        _pattern_detector = PatternDetector()
    return _pattern_detector
