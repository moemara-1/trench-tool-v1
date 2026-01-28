"""
Freshies Wizard Service

Monitors tokens for multi-pattern matching:
- 🍃 Continuous Fresh Buys (5+ min since last update)
- 📈 MarketCap Increase (MC went up X times)
- 🤹‍♀️ Different Funding Sources & Routers (2+ each)
- 🗝️ Freshies Holding (bought but none sold)
- 💤 Old Token (12+ hours old)
- 🪄 All Patterns Matched
"""

import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from collections import Counter, defaultdict

from config import settings
from services.api_clients import get_token_fetcher

logger = logging.getLogger(__name__)


class WizardPattern(Enum):
    """Wizard pattern categories."""
    CONTINUOUS_FRESH_BUYS = "Fresh buys 5 minutes since last update"
    MARKETCAP_INCREASE = "Marketcap since first fresh buy"
    DIFF_FUNDING_ROUTERS = "Fresh buys from Funding Sources and Routers"
    FRESHIES_HOLDING = "Fresh buys without any fresh sales"
    OLD_TOKEN = "Fresh buys on old contract"
    ALL_PATTERNS = "All Patterns Matched"


@dataclass
class FreshBuyEvent:
    """Recorded fresh buy event with details."""
    timestamp: datetime
    wallet: str
    sol_amount: float
    router: Optional[str] = None
    funding_source: Optional[str] = None


@dataclass
class TokenWizardState:
    """Tracks wizard-related state for a token."""
    token_address: str
    symbol: str = "???"
    name: str = "Unknown"
    launchpad: str = ""
    launchpad_emoji: str = ""
    
    # Market cap tracking
    current_mc: Optional[float] = None
    first_fresh_mc: Optional[float] = None
    age_minutes: int = 0
    
    # Fresh buy tracking
    fresh_buys: List[FreshBuyEvent] = field(default_factory=list)
    fresh_sell_count: int = 0
    partial_sell_count: int = 0
    dormant_buy_count: int = 0
    
    # Timestamps
    first_fresh_time: Optional[datetime] = None
    last_update_time: Optional[datetime] = None
    
    # Pattern triggers
    patterns_triggered: Set[WizardPattern] = field(default_factory=set)
    pattern_trigger_count: Dict[WizardPattern, int] = field(default_factory=lambda: defaultdict(int))
    last_alert_time: Dict[WizardPattern, datetime] = field(default_factory=dict)
    
    # Social links
    telegram_link: Optional[str] = None
    twitter_link: Optional[str] = None
    website_link: Optional[str] = None


# Market cap bracket emojis
MC_BRACKETS = [
    (500_000, "🟦"),
    (200_000, "🟩"),
    (100_000, "🟨"),
    (45_000, "🟧"),
]

# Fresh wallet count emojis
FRESH_COUNT_EMOJIS = [
    (100, "1️⃣0️⃣0️⃣"),
    (50, "5️⃣0️⃣"),
    (35, "3️⃣5️⃣"),
    (25, "2️⃣5️⃣"),
    (15, "1️⃣5️⃣"),
    (10, "🔟"),
]

# Router emojis
ROUTER_EMOJIS = {
    "axiom": "🔳",
    "padre": "🏮",
    "telemetry": "🐶",
    "nova": "♋️",
    "banana": "🍌",
    "maestro": "Ⓜ️",
    "trojan": "🔱",
    "bloom": "🌸",
    "mintech": "📱",
    "bonk": "🐕",
    "photon": "🔆",
}

# Launchpad emojis
LAUNCHPAD_EMOJIS = {
    "pump.fun": "💊",
    "moonshot": "🌙",
    "bonk": "🐕",
    "raydium": "🔮",
    "sugar": "🍭",
}

# Wizard thresholds
THRESHOLDS = {
    "continuous_fresh_interval_mins": 5,  # Alert if fresh buy 5+ mins after last
    "mc_increase_multiplier": 2,  # MC went up 2x+
    "min_funding_sources": 2,  # Need 2+ different funding sources
    "min_routers": 2,  # Need 2+ different routers
    "old_token_hours": 12,  # Token age for "old token" pattern
    "alert_cooldown_mins": 5,  # Don't re-alert same pattern too quickly
}


class FreshiesWizard:
    """Monitors tokens for multi-pattern wizard alerts."""
    
    def __init__(self):
        self._tokens: Dict[str, TokenWizardState] = {}
        self._telegram = None
    
    def _get_telegram(self):
        if self._telegram is None:
            from alerts.telegram_bot import get_telegram_bot
            self._telegram = get_telegram_bot()
        return self._telegram
    
    def _get_or_create_token(self, token_address: str) -> TokenWizardState:
        """Get or create token wizard state."""
        if token_address not in self._tokens:
            self._tokens[token_address] = TokenWizardState(token_address=token_address)
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
        fresh_sells: int = None,
        partial_sells: int = None,
        dormant_buys: int = None,
        telegram_link: str = None,
        twitter_link: str = None,
        website_link: str = None,
    ):
        """Update token metadata."""
        state = self._get_or_create_token(token_address)
        
        if symbol:
            state.symbol = symbol
        if name:
            state.name = name
        if market_cap is not None:
            state.current_mc = market_cap
            # Track first MC when first fresh buy happens
            if state.first_fresh_mc is None and state.fresh_buys:
                state.first_fresh_mc = market_cap
        if age_minutes is not None:
            state.age_minutes = age_minutes
        if launchpad:
            state.launchpad = launchpad
        if launchpad_emoji:
            state.launchpad_emoji = launchpad_emoji
        if fresh_sells is not None:
            state.fresh_sell_count = fresh_sells
        if partial_sells is not None:
            state.partial_sell_count = partial_sells
        if dormant_buys is not None:
            state.dormant_buy_count = dormant_buys
        if telegram_link:
            state.telegram_link = telegram_link
        if twitter_link:
            state.twitter_link = twitter_link
        if website_link:
            state.website_link = website_link
    
    async def record_fresh_buy(
        self,
        token_address: str,
        wallet: str,
        sol_amount: float,
        router: str = None,
        funding_source: str = None,
    ):
        """Record a fresh wallet buy and check wizard patterns."""
        state = self._get_or_create_token(token_address)
        now = datetime.utcnow()
        
        event = FreshBuyEvent(
            timestamp=now,
            wallet=wallet,
            sol_amount=sol_amount,
            router=router,
            funding_source=funding_source,
        )
        
        state.fresh_buys.append(event)
        
        # Track first fresh time and MC
        if state.first_fresh_time is None:
            state.first_fresh_time = now
            state.first_fresh_mc = state.current_mc
        
        # Check all wizard patterns
        await self._check_wizard_patterns(token_address)
        
        # Update last activity time
        state.last_update_time = now
    
    async def _check_wizard_patterns(self, token_address: str):
        """Check all wizard pattern conditions."""
        state = self._tokens.get(token_address)
        if not state or not state.fresh_buys:
            return
        
        now = datetime.utcnow()
        patterns_matched = set()
        
        # === 🍃 CONTINUOUS FRESH BUYS ===
        # New fresh buy 5+ minutes after last update
        if state.last_update_time:
            mins_since_last = (now - state.last_update_time).total_seconds() / 60
            if mins_since_last >= THRESHOLDS["continuous_fresh_interval_mins"]:
                patterns_matched.add(WizardPattern.CONTINUOUS_FRESH_BUYS)
        
        # === 📈 MARKETCAP INCREASE ===
        # MC went up X times since first fresh buy
        if state.first_fresh_mc and state.current_mc:
            mc_multiplier = state.current_mc / state.first_fresh_mc
            if mc_multiplier >= THRESHOLDS["mc_increase_multiplier"]:
                patterns_matched.add(WizardPattern.MARKETCAP_INCREASE)
        
        # === 🤹‍♀️ DIFFERENT FUNDING SOURCES & ROUTERS ===
        funding_sources = set(e.funding_source for e in state.fresh_buys if e.funding_source)
        routers = set(e.router for e in state.fresh_buys if e.router)
        
        if len(funding_sources) >= THRESHOLDS["min_funding_sources"] and len(routers) >= THRESHOLDS["min_routers"]:
            patterns_matched.add(WizardPattern.DIFF_FUNDING_ROUTERS)
        
        # === 🗝️ FRESHIES HOLDING ===
        # Fresh wallets bought but none sold
        if state.fresh_buys and state.fresh_sell_count == 0:
            patterns_matched.add(WizardPattern.FRESHIES_HOLDING)
        
        # === 💤 OLD TOKEN ===
        # Token is 12+ hours old
        if state.age_minutes >= THRESHOLDS["old_token_hours"] * 60:
            patterns_matched.add(WizardPattern.OLD_TOKEN)
        
        # === 🪄 ALL PATTERNS MATCHED ===
        core_patterns = {
            WizardPattern.CONTINUOUS_FRESH_BUYS,
            WizardPattern.MARKETCAP_INCREASE,
            WizardPattern.DIFF_FUNDING_ROUTERS,
            WizardPattern.FRESHIES_HOLDING,
        }
        if core_patterns.issubset(patterns_matched):
            patterns_matched.add(WizardPattern.ALL_PATTERNS)
        
        # Trigger alerts for new patterns
        for pattern in patterns_matched:
            if self._should_alert(state, pattern):
                await self._trigger_wizard_alert(token_address, pattern, patterns_matched)
    
    def _should_alert(self, state: TokenWizardState, pattern: WizardPattern) -> bool:
        """Check if we should send alert (cooldown check)."""
        now = datetime.utcnow()
        cooldown = timedelta(minutes=THRESHOLDS["alert_cooldown_mins"])
        
        last_alert = state.last_alert_time.get(pattern)
        if last_alert and (now - last_alert) < cooldown:
            return False
        
        return True
    
    async def _trigger_wizard_alert(
        self,
        token_address: str,
        pattern: WizardPattern,
        all_matched: Set[WizardPattern],
    ):
        """Trigger a wizard pattern alert."""
        state = self._tokens.get(token_address)
        if not state:
            return
        
        now = datetime.utcnow()
        
        # Update trigger count and time
        state.pattern_trigger_count[pattern] += 1
        state.last_alert_time[pattern] = now
        state.patterns_triggered.add(pattern)
        trigger_count = state.pattern_trigger_count[pattern]
        
        # Format alert (async to fetch pair address for Axiom)
        alert = await self._format_wizard_alert(state, pattern, trigger_count, all_matched)
        
        # Send to Telegram (wizard topic)
        topic_id = getattr(settings, 'telegram_wizard_topic_id', None)
        if topic_id and topic_id > 0:
            await self._get_telegram().send_alert(alert, topic_id=topic_id)
        else:
            # Fall back to patterns topic
            topic_id = getattr(settings, 'telegram_patterns_topic_id', None)
            if topic_id and topic_id > 0:
                await self._get_telegram().send_alert(alert, topic_id=topic_id)
            else:
                await self._get_telegram().send_alert(alert)
        
        logger.info(f"🧙‍♂️ Wizard pattern: {pattern.value} for {state.symbol}")
    
    async def _format_wizard_alert(
        self,
        state: TokenWizardState,
        pattern: WizardPattern,
        trigger_count: int,
        all_matched: List[WizardPattern],
    ) -> str:
        """Format BBB-style wizard alert."""
        lines = []
        
        # Build indicator emojis
        indicators = []
        
        # First mention
        is_first = trigger_count == 1 and pattern == list(state.patterns_triggered)[0] if state.patterns_triggered else True
        if is_first:
            indicators.append("⭐️")
        
        # All patterns matched
        if WizardPattern.ALL_PATTERNS in all_matched:
            indicators.append("🪄")
        
        # Fresh wallet count emoji
        fresh_count = len(state.fresh_buys)
        for threshold, emoji in FRESH_COUNT_EMOJIS:
            if fresh_count >= threshold:
                indicators.append(emoji)
                break
        
        # MC bracket emoji
        if state.current_mc:
            for threshold, emoji in MC_BRACKETS:
                if state.current_mc >= threshold:
                    indicators.append(emoji)
                    break
        
        indicator_str = " ".join(indicators)
        
        # Line 1: Pattern info
        pattern_desc = self._get_pattern_description(state, pattern)
        lines.append(f"[{trigger_count}] {indicator_str} {pattern_desc}")
        
        # Line 2: Token info
        age_str = self._format_age(state.age_minutes)
        mc_str = self._format_number(state.current_mc) if state.current_mc else "?"
        lines.append(f"${state.symbol} {state.name} {age_str} {mc_str}")
        
        # Line 3: Contract
        lines.append(f"<code>{state.token_address}</code>")
        
        # Line 4: Wizard Stats
        lines.append("")
        
        # Router emojis for stats line
        routers = set(e.router for e in state.fresh_buys if e.router)
        router_emojis = " ".join(ROUTER_EMOJIS.get(r.lower(), "") for r in routers if r)
        launchpad_emoji = state.launchpad_emoji or LAUNCHPAD_EMOJIS.get(state.launchpad, "")
        
        lines.append(f"📊 Stats:{launchpad_emoji} {router_emojis}")
        
        # Total SOL
        total_sol = sum(e.sol_amount for e in state.fresh_buys)
        lines.append(f"├ Total: {total_sol:.2f}")
        
        # Freshie details
        fresh_count = len(state.fresh_buys)
        lines.append(f"├ Freshie Details: 👶 {fresh_count} ♦️ {state.fresh_sell_count} 🔶 {state.partial_sell_count} ⏳ {state.dormant_buy_count}")
        
        # Top 5 amounts
        top_amounts = sorted([e.sol_amount for e in state.fresh_buys], reverse=True)[:5]
        amounts_str = ",".join(f"{a:.2f}" for a in top_amounts)
        lines.append(f"├ Amounts: {amounts_str}")
        
        # Routers used
        router_counter = Counter(e.router for e in state.fresh_buys if e.router)
        if router_counter:
            router_str = ", ".join(f"{count}x {router.title()}" for router, count in router_counter.most_common(3))
            lines.append(f"├ Routers: {router_str}")
        
        # Social links
        links = []
        if state.telegram_link:
            links.append(f'<a href="{state.telegram_link}">Telegram</a>')
        if state.twitter_link:
            links.append(f'<a href="{state.twitter_link}">Twitter</a>')
        if state.website_link:
            links.append(f'<a href="{state.website_link}">Website</a>')
        if links:
            lines.append(f"├ Links: {' | '.join(links)}")
        
        # Funding sources
        funding_counter = Counter(e.funding_source for e in state.fresh_buys if e.funding_source)
        if funding_counter:
            funding_str = ", ".join(f"{count}x {source}" for source, count in funding_counter.most_common(5))
            lines.append(f"└ Funding: {funding_str}")
        
        # Trading links (async to get pair address for Axiom)
        trading_links = await self._format_trading_links_async(state.token_address)
        lines.append(trading_links)
        
        return "\n".join(lines)
    
    def _get_pattern_description(self, state: TokenWizardState, pattern: WizardPattern) -> str:
        """Get descriptive text for pattern."""
        fresh_count = len(state.fresh_buys)
        
        if pattern == WizardPattern.CONTINUOUS_FRESH_BUYS:
            return f"{fresh_count} {pattern.value}"
        
        elif pattern == WizardPattern.MARKETCAP_INCREASE:
            if state.first_fresh_mc and state.current_mc:
                multiplier = int(state.current_mc / state.first_fresh_mc)
                return f"{multiplier}x {pattern.value}"
            return pattern.value
        
        elif pattern == WizardPattern.DIFF_FUNDING_ROUTERS:
            funding_sources = set(e.funding_source for e in state.fresh_buys if e.funding_source)
            routers = set(e.router for e in state.fresh_buys if e.router)
            return f"{fresh_count} Fresh buys from {len(funding_sources)} Funding Sources and {len(routers)} Routers"
        
        elif pattern == WizardPattern.FRESHIES_HOLDING:
            return f"{fresh_count} {pattern.value}"
        
        elif pattern == WizardPattern.OLD_TOKEN:
            age_str = self._format_age(state.age_minutes)
            return f"{fresh_count} Fresh buys on {age_str} old contract"
        
        elif pattern == WizardPattern.ALL_PATTERNS:
            return f"🪄 {pattern.value}"
        
        return pattern.value
    
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
        
        # Use double quotes for HTML attributes (matching solana_listener.py format)
        return f"""<a href="https://photon-sol.tinyastro.io/en/lp/{token_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={token_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={token_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{token_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={token_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={token_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={token_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={token_address}">NE</a> | <a href="https://dexscreener.com/solana/{token_address}">DS</a> | <a href="https://pump.fun/{token_address}">PF</a>"""
    



# Singleton instance
_freshies_wizard: Optional[FreshiesWizard] = None


def get_freshies_wizard() -> FreshiesWizard:
    """Get singleton freshies wizard."""
    global _freshies_wizard
    if _freshies_wizard is None:
        _freshies_wizard = FreshiesWizard()
    return _freshies_wizard
