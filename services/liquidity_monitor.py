"""
Trench Tool V1 - Liquidity Monitor
Monitors liquidity inflows, locks, and ruggability.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

from models import Token, AlertPriority

logger = logging.getLogger(__name__)


class LockPlatform(str, Enum):
    """Liquidity lock platforms."""
    STREAMFLOW = "Streamflow"
    TEAM_FINANCE = "Team Finance"
    UNICRYPT = "Unicrypt"
    UNCX = "UNCX"
    UNKNOWN = "Unknown"


@dataclass
class LiquidityInfo:
    """Information about a token's liquidity."""
    token_address: str
    total_liquidity_usd: float
    liquidity_ratio: float  # Liquidity / Market Cap
    
    # Lock info
    is_locked: bool
    lock_platform: Optional[LockPlatform]
    lock_duration_days: Optional[int]
    unlock_date: Optional[datetime]
    locked_percent: float
    
    # Pool info
    pool_address: Optional[str]
    dex_name: str
    
    # Risk assessment
    rug_risk_score: float  # 0-100


@dataclass
class LiquidityEvent:
    """A liquidity change event."""
    token_address: str
    event_type: str  # "add", "remove", "lock", "unlock"
    amount_usd: float
    timestamp: datetime
    tx_signature: str
    wallet_address: str


class LiquidityMonitor:
    """
    Monitors liquidity for tokens.
    
    Features:
    - Track liquidity additions/removals
    - Detect liquidity locks (Streamflow, etc.)
    - Calculate rug risk based on liquidity
    - Alert on suspicious liquidity movements
    """
    
    def __init__(self):
        # Streamflow program ID for lock detection
        self.streamflow_program_id = "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m"
        
        # Track liquidity by token
        self._liquidity_cache: Dict[str, LiquidityInfo] = {}
        self._events: List[LiquidityEvent] = []
        
        # Thresholds
        self.min_liquidity_usd = 5000
        self.healthy_liquidity_ratio = 0.1  # 10% of MC
    
    def update_liquidity(
        self,
        token_address: str,
        liquidity_usd: float,
        market_cap: float = None,
        is_locked: bool = False,
        lock_platform: LockPlatform = None,
        lock_duration_days: int = None,
        locked_percent: float = 0,
        pool_address: str = None,
        dex_name: str = "Unknown",
    ) -> LiquidityInfo:
        """Update liquidity info for a token."""
        
        # Calculate ratio
        ratio = liquidity_usd / market_cap if market_cap and market_cap > 0 else 0
        
        # Calculate rug risk
        rug_risk = self._calculate_rug_risk(
            liquidity_usd=liquidity_usd,
            ratio=ratio,
            is_locked=is_locked,
            locked_percent=locked_percent,
        )
        
        info = LiquidityInfo(
            token_address=token_address,
            total_liquidity_usd=liquidity_usd,
            liquidity_ratio=ratio,
            is_locked=is_locked,
            lock_platform=lock_platform,
            lock_duration_days=lock_duration_days,
            unlock_date=datetime.utcnow() + timedelta(days=lock_duration_days) if lock_duration_days else None,
            locked_percent=locked_percent,
            pool_address=pool_address,
            dex_name=dex_name,
            rug_risk_score=rug_risk,
        )
        
        self._liquidity_cache[token_address] = info
        return info
    
    def _calculate_rug_risk(
        self,
        liquidity_usd: float,
        ratio: float,
        is_locked: bool,
        locked_percent: float,
    ) -> float:
        """Calculate rug risk score (0-100)."""
        risk = 0
        
        # Low liquidity (0-30)
        if liquidity_usd < 1000:
            risk += 30
        elif liquidity_usd < 5000:
            risk += 20
        elif liquidity_usd < 20000:
            risk += 10
        
        # Low ratio (0-25)
        if ratio < 0.02:
            risk += 25
        elif ratio < 0.05:
            risk += 15
        elif ratio < 0.1:
            risk += 5
        
        # Not locked (0-30)
        if not is_locked:
            risk += 20
        elif locked_percent < 50:
            risk += 10
        elif locked_percent < 80:
            risk += 5
        
        # Bonus for fully locked
        if is_locked and locked_percent >= 95:
            risk = max(0, risk - 15)
        
        return min(100, risk)
    
    def add_event(
        self,
        token_address: str,
        event_type: str,
        amount_usd: float,
        wallet_address: str,
        tx_signature: str,
    ) -> LiquidityEvent:
        """Record a liquidity event."""
        event = LiquidityEvent(
            token_address=token_address,
            event_type=event_type,
            amount_usd=amount_usd,
            timestamp=datetime.utcnow(),
            tx_signature=tx_signature,
            wallet_address=wallet_address,
        )
        self._events.append(event)
        return event
    
    def is_streamflow_lock(self, program_ids: List[str]) -> bool:
        """Check if transaction is a Streamflow lock."""
        return self.streamflow_program_id in program_ids
    
    def get_liquidity_info(self, token_address: str) -> Optional[LiquidityInfo]:
        """Get cached liquidity info for a token."""
        return self._liquidity_cache.get(token_address)
    
    def get_recent_events(
        self,
        token_address: str = None,
        event_type: str = None,
        hours: int = 24,
    ) -> List[LiquidityEvent]:
        """Get recent liquidity events."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        events = [e for e in self._events if e.timestamp >= cutoff]
        
        if token_address:
            events = [e for e in events if e.token_address == token_address]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events
    
    def format_liquidity_alert(
        self,
        info: LiquidityInfo,
        token_symbol: str = None,
        event: LiquidityEvent = None,
    ) -> str:
        """Format a liquidity alert message."""
        symbol = token_symbol or "???"
        
        # Determine alert type
        if info.is_locked:
            emoji = "🔒"
            title = "LIQUIDITY LOCKED"
        elif event and event.event_type == "remove":
            emoji = "⚠️"
            title = "LIQUIDITY REMOVED"
        elif event and event.event_type == "add":
            emoji = "💧"
            title = "LIQUIDITY ADDED"
        else:
            emoji = "📊"
            title = "LIQUIDITY UPDATE"
        
        # Risk indicator
        if info.rug_risk_score >= 70:
            risk_emoji = "🔴"
            risk_text = "HIGH RISK"
        elif info.rug_risk_score >= 40:
            risk_emoji = "🟠"
            risk_text = "MEDIUM RISK"
        else:
            risk_emoji = "🟢"
            risk_text = "LOW RISK"
        
        message = f"""
{emoji} <b>{title}</b>

• Token: <b>${symbol}</b>
• Liquidity: <b>${info.total_liquidity_usd:,.0f}</b>
• Ratio: <b>{info.liquidity_ratio:.1%}</b>
• DEX: {info.dex_name}
"""
        
        if info.is_locked:
            message += f"""
🔐 <b>Lock Info:</b>
• Platform: {info.lock_platform.value if info.lock_platform else "Unknown"}
• Locked: {info.locked_percent:.0f}%
• Duration: {info.lock_duration_days or "Unknown"} days
"""
        
        message += f"""
{risk_emoji} Rug Risk: <b>{risk_text}</b> ({info.rug_risk_score:.0f}/100)

<code>{info.token_address}</code>
"""
        
        return message.strip()
    
    def get_stats(self) -> dict:
        """Get monitor statistics."""
        return {
            "tracked_tokens": len(self._liquidity_cache),
            "total_events": len(self._events),
            "locked_tokens": sum(1 for info in self._liquidity_cache.values() if info.is_locked),
        }


# Singleton
_liquidity_monitor: LiquidityMonitor | None = None


def get_liquidity_monitor() -> LiquidityMonitor:
    """Get the singleton liquidity monitor."""
    global _liquidity_monitor
    if _liquidity_monitor is None:
        _liquidity_monitor = LiquidityMonitor()
    return _liquidity_monitor
