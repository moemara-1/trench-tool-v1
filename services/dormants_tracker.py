"""
Trench Tool V1 - Dormants Tracker
Tracks wallets that have been inactive for extended periods and suddenly become active.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Wallet, Token, Freshie, Alert, WalletType, AlertPriority, TradeAction

logger = logging.getLogger(__name__)


@dataclass
class DormantWalletInfo:
    """Information about a dormant wallet that woke up."""
    address: str
    dormant_days: int
    last_activity: datetime
    wake_up_time: datetime
    tokens_held: int
    total_value_sol: float
    is_big_dormant: bool  # > 100 tokens
    is_semi_dormant: bool  # 7-30 days inactive


class DormantsTracker:
    """
    Tracks dormant wallets and detects when they become active.
    
    Dormant Categories:
    - Full Dormant: Inactive 30+ days
    - Semi-Dormant: Inactive 7-30 days
    - Big Dormant: Dormant with 100+ token types held
    """
    
    def __init__(self):
        self.dormant_threshold_days = settings.dormant_wallet_min_inactive_days
        self.semi_dormant_min_days = 7
        self.big_dormant_token_threshold = 100
        
        # Track recently alerted dormants to avoid spam
        self._alerted_dormants: dict[str, datetime] = {}
        self._alert_cooldown = timedelta(hours=1)
    
    def classify_dormant(
        self,
        last_activity: datetime,
        tokens_held: int = 0,
    ) -> Tuple[bool, bool, bool]:
        """
        Classify a wallet's dormancy status.
        
        Returns:
            Tuple of (is_dormant, is_semi_dormant, is_big_dormant)
        """
        now = datetime.utcnow()
        inactive_days = (now - last_activity).days if last_activity else 999
        
        is_dormant = inactive_days >= self.dormant_threshold_days
        is_semi_dormant = self.semi_dormant_min_days <= inactive_days < self.dormant_threshold_days
        is_big_dormant = is_dormant and tokens_held >= self.big_dormant_token_threshold
        
        return is_dormant, is_semi_dormant, is_big_dormant
    
    def get_dormant_priority(self, info: DormantWalletInfo) -> AlertPriority:
        """Determine alert priority for a dormant wallet waking up."""
        if info.is_big_dormant:
            return AlertPriority.CRITICAL
        if info.dormant_days >= 180:  # 6+ months
            return AlertPriority.CRITICAL
        if info.dormant_days >= 90:  # 3+ months
            return AlertPriority.HIGH
        if info.dormant_days >= 30:
            return AlertPriority.MEDIUM
        return AlertPriority.LOW
    
    def should_alert(self, wallet_address: str) -> bool:
        """Check if we should send an alert for this dormant wallet."""
        now = datetime.utcnow()
        
        if wallet_address in self._alerted_dormants:
            last_alert = self._alerted_dormants[wallet_address]
            if now - last_alert < self._alert_cooldown:
                return False
        
        self._alerted_dormants[wallet_address] = now
        return True
    
    async def check_wallet_dormancy(
        self,
        session: AsyncSession,
        wallet: Wallet,
    ) -> Optional[DormantWalletInfo]:
        """
        Check if a wallet is dormant and return info if so.
        
        Returns DormantWalletInfo if wallet is dormant, None otherwise.
        """
        if not wallet.last_activity_at:
            return None
        
        is_dormant, is_semi_dormant, is_big_dormant = self.classify_dormant(
            last_activity=wallet.last_activity_at,
            tokens_held=wallet.total_transactions,  # Using tx count as proxy
        )
        
        if not (is_dormant or is_semi_dormant):
            return None
        
        inactive_days = (datetime.utcnow() - wallet.last_activity_at).days
        
        return DormantWalletInfo(
            address=wallet.address,
            dormant_days=inactive_days,
            last_activity=wallet.last_activity_at,
            wake_up_time=datetime.utcnow(),
            tokens_held=wallet.total_transactions,
            total_value_sol=wallet.total_volume_sol,
            is_big_dormant=is_big_dormant,
            is_semi_dormant=is_semi_dormant,
        )
    
    async def get_dormant_wallets(
        self,
        session: AsyncSession,
        limit: int = 100,
        min_inactive_days: int = None,
    ) -> List[Wallet]:
        """Get list of dormant wallets from database."""
        min_days = min_inactive_days or self.dormant_threshold_days
        cutoff_date = datetime.utcnow() - timedelta(days=min_days)
        
        result = await session.execute(
            select(Wallet)
            .where(
                and_(
                    Wallet.last_activity_at < cutoff_date,
                    Wallet.last_activity_at.isnot(None),
                )
            )
            .order_by(Wallet.last_activity_at.asc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def get_big_dormants(
        self,
        session: AsyncSession,
        limit: int = 50,
    ) -> List[Wallet]:
        """Get dormant wallets with high token counts."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.dormant_threshold_days)
        
        result = await session.execute(
            select(Wallet)
            .where(
                and_(
                    Wallet.last_activity_at < cutoff_date,
                    Wallet.total_transactions >= self.big_dormant_token_threshold,
                )
            )
            .order_by(Wallet.total_transactions.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def get_semi_dormants(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> List[Wallet]:
        """Get semi-dormant wallets (7-30 days inactive)."""
        now = datetime.utcnow()
        min_cutoff = now - timedelta(days=self.dormant_threshold_days)
        max_cutoff = now - timedelta(days=self.semi_dormant_min_days)
        
        result = await session.execute(
            select(Wallet)
            .where(
                and_(
                    Wallet.last_activity_at >= min_cutoff,
                    Wallet.last_activity_at < max_cutoff,
                )
            )
            .order_by(Wallet.last_activity_at.asc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    def format_dormant_alert(
        self,
        info: DormantWalletInfo,
        token_symbol: str = None,
        token_address: str = None,
        amount_sol: float = None,
    ) -> str:
        """Format a dormant wallet alert message."""
        priority = self.get_dormant_priority(info)
        priority_emoji = {
            AlertPriority.CRITICAL: "🔴",
            AlertPriority.HIGH: "🟠",
            AlertPriority.MEDIUM: "🟡",
            AlertPriority.LOW: "🟢",
        }.get(priority, "🟡")
        
        dormant_type = "BIG DORMANT" if info.is_big_dormant else (
            "SEMI-DORMANT" if info.is_semi_dormant else "DORMANT"
        )
        
        short_wallet = f"{info.address[:6]}...{info.address[-4:]}"
        
        message = f"""
{priority_emoji} <b>⏳ {dormant_type} WALLET ALERT</b>

• Wallet inactive for <b>{info.dormant_days} days</b> is now ACTIVE!
• Wallet: <code>{short_wallet}</code>
"""
        
        if token_symbol and amount_sol:
            message += f"""
• Token: <b>${token_symbol}</b>
• Amount: <b>{amount_sol:.2f} SOL</b>
"""
        
        if token_address:
            message += f"""
<b>Contract:</b>
<code>{token_address}</code>

<a href="https://dexscreener.com/solana/{token_address}">DexScreener</a> | <a href="https://birdeye.so/token/{token_address}">Birdeye</a>
"""
        
        return message.strip()
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "alerted_dormants": len(self._alerted_dormants),
            "dormant_threshold_days": self.dormant_threshold_days,
            "semi_dormant_min_days": self.semi_dormant_min_days,
        }


# Singleton
_dormants_tracker: DormantsTracker | None = None


def get_dormants_tracker() -> DormantsTracker:
    """Get the singleton dormants tracker."""
    global _dormants_tracker
    if _dormants_tracker is None:
        _dormants_tracker = DormantsTracker()
    return _dormants_tracker
