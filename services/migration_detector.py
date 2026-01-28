"""
Trench Tool V1 - Migration & Vanish Detector
Detects token migrations, vanish buys/sells, and contract disappearances.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set
from dataclasses import dataclass
from enum import Enum

from models import Token, AlertPriority

logger = logging.getLogger(__name__)


class MigrationType(str, Enum):
    """Types of token migrations."""
    V1_TO_V2 = "v1_to_v2"           # Standard version upgrade
    RELAUNCH = "relaunch"           # Same dev, new token
    PUMP_TO_RAYDIUM = "pf_raydium"  # Pump.fun to Raydium migration
    CROSS_CHAIN = "cross_chain"     # Bridge to another chain


@dataclass
class MigrationInfo:
    """Information about a token migration."""
    old_token_address: str
    new_token_address: str
    migration_type: MigrationType
    detected_at: datetime
    deployer_address: Optional[str]
    migration_ratio: Optional[float]  # How many new tokens per old
    is_late_migration: bool  # Delayed bonding curve exit


@dataclass
class VanishEvent:
    """A vanish event (buy/sell of token that no longer exists)."""
    token_address: str
    event_type: str  # "vanish_buy" or "vanish_sell"
    wallet_address: str
    amount_sol: float
    detected_at: datetime
    tx_signature: str
    is_potential_rug: bool


class MigrationDetector:
    """
    Detects token migrations and relaunches.
    
    Migration indicators:
    - Same deployer, new contract
    - Social media references to "V2"
    - Holder migration patterns
    - Pump.fun late exits
    """
    
    def __init__(self):
        # Track deployer -> tokens mapping
        self._deployer_tokens: Dict[str, List[str]] = {}
        self._migrations: List[MigrationInfo] = []
        
        # Track old migrations (potential insider knowledge)
        self._known_migrated_tokens: Set[str] = set()
    
    def add_token_deployment(
        self,
        token_address: str,
        deployer_address: str,
    ):
        """Record a new token deployment."""
        if deployer_address not in self._deployer_tokens:
            self._deployer_tokens[deployer_address] = []
        
        self._deployer_tokens[deployer_address].append(token_address)
        
        # Check if this deployer has previous tokens (potential migration)
        if len(self._deployer_tokens[deployer_address]) > 1:
            self._check_for_migration(deployer_address)
    
    def _check_for_migration(self, deployer_address: str):
        """Check if a deployer's new token is a migration."""
        tokens = self._deployer_tokens[deployer_address]
        if len(tokens) < 2:
            return
        
        old_token = tokens[-2]
        new_token = tokens[-1]
        
        # This is a simplified check - in production would verify more signals
        migration = MigrationInfo(
            old_token_address=old_token,
            new_token_address=new_token,
            migration_type=MigrationType.RELAUNCH,
            detected_at=datetime.utcnow(),
            deployer_address=deployer_address,
            migration_ratio=None,
            is_late_migration=False,
        )
        
        self._migrations.append(migration)
        self._known_migrated_tokens.add(old_token)
        logger.info(f"Migration detected: {old_token[:8]}... -> {new_token[:8]}...")
    
    def detect_pump_migration(
        self,
        token_address: str,
        bonding_curve_complete: bool,
        time_to_complete_hours: float,
    ) -> Optional[MigrationInfo]:
        """
        Detect Pump.fun to Raydium migrations.
        
        Late migrations (delayed bonding curve exit) are suspicious.
        """
        if not bonding_curve_complete:
            return None
        
        is_late = time_to_complete_hours > 24  # More than 24h is "late"
        
        migration = MigrationInfo(
            old_token_address=token_address,
            new_token_address=token_address,  # Same token, just graduated
            migration_type=MigrationType.PUMP_TO_RAYDIUM,
            detected_at=datetime.utcnow(),
            deployer_address=None,
            migration_ratio=1.0,
            is_late_migration=is_late,
        )
        
        self._migrations.append(migration)
        return migration
    
    def get_deployer_history(self, deployer_address: str) -> List[str]:
        """Get all tokens deployed by an address."""
        return self._deployer_tokens.get(deployer_address, [])
    
    def is_migration_token(self, token_address: str) -> bool:
        """Check if a token was migrated from another."""
        return token_address in self._known_migrated_tokens
    
    def get_recent_migrations(self, hours: int = 24) -> List[MigrationInfo]:
        """Get migrations from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [m for m in self._migrations if m.detected_at >= cutoff]
    
    def format_migration_alert(
        self,
        migration: MigrationInfo,
        old_symbol: str = None,
        new_symbol: str = None,
    ) -> str:
        """Format a migration alert message."""
        old_sym = old_symbol or "???"
        new_sym = new_symbol or "???"
        
        if migration.is_late_migration:
            emoji = "⚠️"
            title = "LATE MIGRATION DETECTED"
            warning = "\n<b>⚠️ Late migration - potential insider pattern!</b>"
        else:
            emoji = "🔄"
            title = "TOKEN MIGRATION"
            warning = ""
        
        short_old = f"{migration.old_token_address[:6]}...{migration.old_token_address[-4:]}"
        short_new = f"{migration.new_token_address[:6]}...{migration.new_token_address[-4:]}"
        
        message = f"""
{emoji} <b>{title}</b>

• Old: <b>${old_sym}</b> (<code>{short_old}</code>)
• New: <b>${new_sym}</b> (<code>{short_new}</code>)
• Type: {migration.migration_type.value}
{warning}

New Contract:
<code>{migration.new_token_address}</code>

<a href="https://dexscreener.com/solana/{migration.new_token_address}">DexScreener</a>
"""
        return message.strip()
    
    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "tracked_deployers": len(self._deployer_tokens),
            "total_migrations": len(self._migrations),
            "late_migrations": sum(1 for m in self._migrations if m.is_late_migration),
        }


class VanishDetector:
    """
    Detects vanish buys and vanish sells.
    
    Vanish patterns:
    - Tokens bought but contract no longer exists
    - Large sells followed by contract disappearance
    - Honeypot indicators
    """
    
    def __init__(self):
        self._vanish_events: List[VanishEvent] = []
        self._disappeared_tokens: Set[str] = set()
    
    def mark_token_disappeared(self, token_address: str):
        """Mark a token as disappeared/invalid."""
        self._disappeared_tokens.add(token_address)
        logger.warning(f"Token marked as disappeared: {token_address[:8]}...")
    
    def is_disappeared(self, token_address: str) -> bool:
        """Check if a token has disappeared."""
        return token_address in self._disappeared_tokens
    
    def record_vanish_event(
        self,
        token_address: str,
        event_type: str,
        wallet_address: str,
        amount_sol: float,
        tx_signature: str,
    ) -> VanishEvent:
        """Record a vanish buy or sell event."""
        # Large sells before disappearance are potential rugs
        is_potential_rug = (
            event_type == "vanish_sell" and 
            amount_sol >= 10 and
            token_address in self._disappeared_tokens
        )
        
        event = VanishEvent(
            token_address=token_address,
            event_type=event_type,
            wallet_address=wallet_address,
            amount_sol=amount_sol,
            detected_at=datetime.utcnow(),
            tx_signature=tx_signature,
            is_potential_rug=is_potential_rug,
        )
        
        self._vanish_events.append(event)
        return event
    
    def format_vanish_alert(self, event: VanishEvent) -> str:
        """Format a vanish event alert."""
        if event.is_potential_rug:
            emoji = "🚨"
            title = "POTENTIAL RUG - VANISH SELL"
        elif event.event_type == "vanish_sell":
            emoji = "⚠️"
            title = "VANISH SELL"
        else:
            emoji = "👻"
            title = "VANISH BUY"
        
        short_wallet = f"{event.wallet_address[:6]}...{event.wallet_address[-4:]}"
        short_token = f"{event.token_address[:6]}...{event.token_address[-4:]}"
        
        message = f"""
{emoji} <b>{title}</b>

• Token: <code>{short_token}</code>
• Wallet: <code>{short_wallet}</code>
• Amount: <b>{event.amount_sol:.2f} SOL</b>
• Status: <b>Contract disappeared/invalid</b>
"""
        
        if event.is_potential_rug:
            message += "\n<b>⚠️ LIKELY RUG PULL - Large sell before disappearance!</b>"
        
        return message.strip()
    
    def get_recent_vanishes(self, hours: int = 24) -> List[VanishEvent]:
        """Get vanish events from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [e for e in self._vanish_events if e.detected_at >= cutoff]
    
    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "vanish_events": len(self._vanish_events),
            "disappeared_tokens": len(self._disappeared_tokens),
            "potential_rugs": sum(1 for e in self._vanish_events if e.is_potential_rug),
        }


# Singletons
_migration_detector: MigrationDetector | None = None
_vanish_detector: VanishDetector | None = None


def get_migration_detector() -> MigrationDetector:
    """Get the singleton migration detector."""
    global _migration_detector
    if _migration_detector is None:
        _migration_detector = MigrationDetector()
    return _migration_detector


def get_vanish_detector() -> VanishDetector:
    """Get the singleton vanish detector."""
    global _vanish_detector
    if _vanish_detector is None:
        _vanish_detector = VanishDetector()
    return _vanish_detector
