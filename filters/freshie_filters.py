"""
Trench Tool V1 - Freshies Sub-Filters
Advanced filtering for different types of fresh wallet activity.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Wallet, Token, Freshie, WalletType, TradeAction

logger = logging.getLogger(__name__)


class FreshieType(str, Enum):
    """Types of freshie alerts."""
    STANDARD = "standard"      # Regular fresh wallet buy
    BIG = "big"                # > 10 SOL from fresh wallet
    LOW_MC = "low_mc"          # Fresh buy on token < $50k MC
    OLD = "old"                # Wallet that has been holding > 30 days
    TG = "telegram"            # Detected from Telegram community
    WHALE = "whale"            # > 15 SOL
    DOLPHIN = "dolphin"        # 5-15 SOL


@dataclass
class FilteredFreshie:
    """A freshie that passed through filters."""
    freshie: Freshie
    freshie_types: List[FreshieType]
    priority_boost: int  # Additional priority from filters
    emoji_additions: List[str]
    filter_reasons: List[str]


class FreshiesFilters:
    """
    Advanced filtering system for freshies.
    
    Filter Types:
    - Big Freshies: Fresh wallets with purchases > 10 SOL
    - Low MC Freshies: Fresh accumulation at MC < $50k
    - Old Freshies: Wallets holding tokens > 30 days
    - TG Freshies: Community wallet tracking
    """
    
    def __init__(self):
        # Thresholds
        self.big_freshie_threshold_sol = 10.0
        self.low_mc_threshold_usd = 50_000
        self.old_freshie_holding_days = 30
        
        # Telegram community wallets (would be configured by user)
        self._tg_community_wallets: set = set()
        
        # Stats
        self._filter_counts: Dict[FreshieType, int] = {ft: 0 for ft in FreshieType}
    
    def classify_freshie(
        self,
        amount_sol: float,
        wallet_type: WalletType,
        token_market_cap: float = None,
        wallet_age_days: int = 0,
        holding_days: int = 0,
        wallet_address: str = None,
    ) -> List[FreshieType]:
        """
        Classify a freshie into one or more types.
        
        Returns list of applicable FreshieTypes.
        """
        types = []
        
        # Only classify if fresh or dormant wallet
        if wallet_type not in (WalletType.FRESH, WalletType.DORMANT):
            return [FreshieType.STANDARD]
        
        # Whale/Dolphin check
        if amount_sol >= settings.whale_threshold_sol:
            types.append(FreshieType.WHALE)
        elif amount_sol >= settings.dolphin_threshold_sol:
            types.append(FreshieType.DOLPHIN)
        
        # Big Freshie check
        if wallet_type == WalletType.FRESH and amount_sol >= self.big_freshie_threshold_sol:
            types.append(FreshieType.BIG)
        
        # Low MC check
        if token_market_cap and token_market_cap < self.low_mc_threshold_usd:
            types.append(FreshieType.LOW_MC)
        
        # Old Freshie check
        if holding_days >= self.old_freshie_holding_days:
            types.append(FreshieType.OLD)
        
        # TG Community check
        if wallet_address and wallet_address in self._tg_community_wallets:
            types.append(FreshieType.TG)
        
        # Default to standard if no other types
        if not types:
            types.append(FreshieType.STANDARD)
        
        # Update stats
        for ft in types:
            self._filter_counts[ft] += 1
        
        return types
    
    def apply_filters(
        self,
        freshie: Freshie,
        wallet: Wallet,
        token: Token,
        holding_days: int = 0,
    ) -> FilteredFreshie:
        """
        Apply all filters to a freshie and return enriched result.
        """
        types = self.classify_freshie(
            amount_sol=freshie.amount_sol,
            wallet_type=wallet.wallet_type,
            token_market_cap=token.market_cap,
            wallet_age_days=(datetime.utcnow() - wallet.first_activity_at).days if wallet.first_activity_at else 0,
            holding_days=holding_days,
            wallet_address=wallet.address,
        )
        
        # Calculate priority boost
        priority_boost = 0
        if FreshieType.BIG in types:
            priority_boost += 2
        if FreshieType.WHALE in types:
            priority_boost += 3
        if FreshieType.LOW_MC in types:
            priority_boost += 1
        if FreshieType.TG in types:
            priority_boost += 1
        
        # Build emoji additions
        emojis = []
        reasons = []
        
        if FreshieType.BIG in types:
            emojis.append("💎")
            reasons.append(f"Big freshie: {freshie.amount_sol:.1f} SOL")
        
        if FreshieType.LOW_MC in types:
            mc_str = f"${token.market_cap/1000:.1f}K" if token.market_cap else "Unknown"
            emojis.append("🎯")
            reasons.append(f"Low MC: {mc_str}")
        
        if FreshieType.OLD in types:
            emojis.append("🕰️")
            reasons.append(f"Holding {holding_days}+ days")
        
        if FreshieType.TG in types:
            emojis.append("📱")
            reasons.append("TG community wallet")
        
        return FilteredFreshie(
            freshie=freshie,
            freshie_types=types,
            priority_boost=priority_boost,
            emoji_additions=emojis,
            filter_reasons=reasons,
        )
    
    # ==================== FILTER QUERIES ====================
    
    async def get_big_freshies(
        self,
        session: AsyncSession,
        min_sol: float = None,
        limit: int = 50,
        hours: int = 24,
    ) -> List[Freshie]:
        """Get freshies with large purchases."""
        min_amount = min_sol or self.big_freshie_threshold_sol
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await session.execute(
            select(Freshie)
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                and_(
                    Freshie.timestamp >= cutoff,
                    Freshie.amount_sol >= min_amount,
                    Wallet.wallet_type == WalletType.FRESH,
                )
            )
            .order_by(Freshie.amount_sol.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def get_low_mc_freshies(
        self,
        session: AsyncSession,
        max_mc: float = None,
        limit: int = 50,
        hours: int = 24,
    ) -> List[Freshie]:
        """Get freshies on low market cap tokens."""
        max_market_cap = max_mc or self.low_mc_threshold_usd
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await session.execute(
            select(Freshie)
            .join(Token, Freshie.token_address == Token.contract_address)
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                and_(
                    Freshie.timestamp >= cutoff,
                    Token.market_cap < max_market_cap,
                    Token.market_cap > 0,
                    Wallet.wallet_type == WalletType.FRESH,
                )
            )
            .order_by(Token.market_cap.asc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def get_old_freshies(
        self,
        session: AsyncSession,
        min_holding_days: int = None,
        limit: int = 50,
    ) -> List[Freshie]:
        """Get wallets that have been holding for extended periods."""
        min_days = min_holding_days or self.old_freshie_holding_days
        cutoff = datetime.utcnow() - timedelta(days=min_days)
        
        result = await session.execute(
            select(Freshie)
            .where(
                and_(
                    Freshie.timestamp <= cutoff,
                    Freshie.action == TradeAction.BUY,
                    # Still holding - no full sell
                )
            )
            .order_by(Freshie.timestamp.asc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def get_tg_freshies(
        self,
        session: AsyncSession,
        limit: int = 50,
        hours: int = 24,
    ) -> List[Freshie]:
        """Get freshies from Telegram community wallets."""
        if not self._tg_community_wallets:
            return []
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        result = await session.execute(
            select(Freshie)
            .where(
                and_(
                    Freshie.timestamp >= cutoff,
                    Freshie.wallet_address.in_(self._tg_community_wallets),
                )
            )
            .order_by(Freshie.timestamp.desc())
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    # ==================== CONFIGURATION ====================
    
    def add_tg_community_wallet(self, address: str):
        """Add a wallet to the Telegram community tracking list."""
        self._tg_community_wallets.add(address)
        logger.info(f"Added TG community wallet: {address[:8]}...")
    
    def remove_tg_community_wallet(self, address: str):
        """Remove a wallet from the Telegram community tracking list."""
        self._tg_community_wallets.discard(address)
    
    def set_big_freshie_threshold(self, sol_amount: float):
        """Set the threshold for big freshies."""
        self.big_freshie_threshold_sol = sol_amount
    
    def set_low_mc_threshold(self, usd_amount: float):
        """Set the threshold for low MC freshies."""
        self.low_mc_threshold_usd = usd_amount
    
    def get_stats(self) -> dict:
        """Get filter statistics."""
        return {
            "filter_counts": {k.value: v for k, v in self._filter_counts.items()},
            "tg_community_wallets": len(self._tg_community_wallets),
            "thresholds": {
                "big_freshie_sol": self.big_freshie_threshold_sol,
                "low_mc_usd": self.low_mc_threshold_usd,
                "old_freshie_days": self.old_freshie_holding_days,
            },
        }


# Singleton
_freshies_filters: FreshiesFilters | None = None


def get_freshies_filters() -> FreshiesFilters:
    """Get the singleton freshies filters."""
    global _freshies_filters
    if _freshies_filters is None:
        _freshies_filters = FreshiesFilters()
    return _freshies_filters
