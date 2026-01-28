"""
Trench Tool V1 - Freshie Channel Router
Routes alerts to appropriate Telegram channels based on freshie criteria.

Classification:
- Freshies: >0.47 SOL, funded <24h ago, low tx count
- TG Freshies: via bot routers, funded <24h ago, low tx count  
- Old Freshies: funded ≥24h ago, low tx count
- Big Freshies: >7 SOL, funded <24h ago, low tx count
- Low MC Big Freshies: >5 SOL, MC ≤5M, funded <24h ago, low tx count
- Low MC Freshies: MC ≤500k, funded <24h ago, low tx count
"""

import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


class FreshieChannel(str, Enum):
    """Freshie sub-channels."""
    FRESHIES = "freshies"              # >0.47 SOL, funded <24h
    TG_FRESHIES = "tg_freshies"        # Via trading bot routers, funded <24h
    OLD_FRESHIES = "old_freshies"      # Funded ≥24h ago but low tx count
    BIG_FRESHIES = "big_freshies"      # >7 SOL, funded <24h
    LOW_MC_BIG = "low_mc_big"          # >5 SOL, MC ≤5M, funded <24h
    LOW_MC = "low_mc"                  # MC ≤500k, funded <24h


@dataclass
class FreshieClassification:
    """Classification result for a freshie purchase."""
    is_valid_alert: bool  # Whether to send alert
    primary_channel: Optional[FreshieChannel]  # Main channel for title
    all_channels: List[FreshieChannel]  # All matching channels
    
    # Wallet info
    wallet_age_hours: int
    wallet_tx_count: int
    funding_source: str
    funding_time_ago: str  # "2h", "1d", etc.
    
    # Classification
    is_new_freshie: bool   # funded <24h
    is_old_freshie: bool   # funded ≥24h but low tx
    
    # Purchase info
    amount_sol: float
    market_cap: Optional[float]
    is_via_router: bool
    router_name: Optional[str]
    router_emoji: str


# Trading bot routers that qualify for TG Freshies
TG_ROUTERS = {
    "AxioMrEJGD6KTcxKMFbcERDqgcC5L8RoWNPVYLJkEVx": ("Axiom", "🔳"),
    "BANANAjh4azVLbDxD9WPjnQNz3KRdDjxdColhDdGKqpz": ("BananaGun", "🍌"),
    "maestrQf2VqwRLbGpQfh1FBrNv1m9J8z4HqDqYVE3UfR": ("Maestro", "Ⓜ️"),
    "TRJNr5nyjEqAP4zyJFqfKxGxNLKPwF5pJVJiHNxz8zP": ("Trojan", "🔱"),
    "BLoomrTFkvs3WUpEKLvEfpcUcaTRVxsWBZoZ8f7RBxqP": ("Bloom", "🌸"),
    "PadrexYtXkGJZmhKYRvfxCjfNxFGGNpKHHZ8xVYFJjp": ("Padre", "🏮"),
    "MinTeCHnHvxnZHMhMJqZV8qDCYgTEpVcNhzLdPDGMWp": ("Mintech", "📱"),
    "PHoToN111111111111111111111111111111111111": ("Photon", "📸"),
    "BuLLx111111111111111111111111111111111111": ("BullX", "🐂"),
}


class DormantType(str, Enum):
    """Dormant alert subtypes."""
    DORMANTS = "dormants"               # ≥3 SOL, 4+ days inactive
    BIG_DORMANTS = "big_dormants"       # ≥7 SOL, 4+ days inactive
    SEMI_DORMANTS = "semi_dormants"     # ≥1 SOL, low MC, 3+ days inactive


@dataclass
class DormantClassification:
    """Classification result for a dormant wallet purchase."""
    is_valid_alert: bool
    dormant_type: Optional[DormantType]  # Primary dormant type
    
    # Wallet info
    wallet_address: str
    last_active_days: int  # Days since last activity
    last_active_str: str   # "43d" format
    
    # Classification
    is_semi_dormant: bool  # 3-3 days inactive (moderate)
    is_old_dormant: bool   # 4+ days inactive
    is_big_dormant: bool   # ≥7 SOL, 4+ days inactive
    dormant_emoji: str     # 🕰️ or 👴🏻
    
    # Purchase info
    amount_sol: float
    market_cap: Optional[float]
    is_via_router: bool
    router_name: Optional[str]
    router_emoji: str
    
    # Launchpad
    launchpad_name: Optional[str]
    launchpad_emoji: str


class FreshieChannelRouter:
    """
    Routes freshie alerts based on criteria:
    
    - Freshies: >0.47 SOL by wallets funded <24h ago
    - TG Freshies: via bot routers by wallets funded <24h ago
    - Old Freshies: wallets funded ≥24h ago but with low tx count
    - Big Freshies: >7 SOL by wallets funded <24h ago
    - Low MC Big Freshies: >5 SOL, MC ≤5M, funded <24h ago
    - Low MC Freshies: MC ≤500k, funded <24h ago
    """
    
    def __init__(self):
        # Thresholds
        self.min_freshie_sol = settings.min_transaction_sol  # Enforce global setting
        self.big_freshie_sol = 7.0       # Big Freshies threshold
        self.low_mc_big_sol = 5.0        # Low MC Big threshold
        self.low_mc_big_cap = 5_000_000  # $5M
        self.low_mc_cap = 500_000        # $500k
        
        # Fresh vs Old threshold
        self.fresh_hours_threshold = 24  # <24h = fresh, ≥24h = old
        
        # Low tx count threshold
        self.max_tx_count = 50
        
        # Channel chat IDs (to be configured)
        self.channel_ids: Dict[FreshieChannel, str] = {}
    
    def classify(
        self,
        amount_sol: float,
        market_cap: Optional[float],
        hours_since_funding: int,
        wallet_tx_count: int,
        funding_source: str,
        program_ids: List[str],
    ) -> FreshieClassification:
        """Classify a purchase into freshie channels."""
        
        # Check router
        router_name = None
        router_emoji = ""
        is_via_router = False
        for pid in program_ids:
            if pid in TG_ROUTERS:
                router_name, router_emoji = TG_ROUTERS[pid]
                is_via_router = True
                break
        
        # GLOBAL FILTER: Enforce minimum SOL threshold for ALL freshie types
        # This prevents 0.00 SOL or dust alerts from slipping through as "low mc" or "tg freshies"
        if amount_sol < self.min_freshie_sol:
             return FreshieClassification(
                is_valid_alert=False,
                primary_channel=None,
                all_channels=[],
                wallet_age_hours=hours_since_funding,
                wallet_tx_count=wallet_tx_count,
                funding_source=funding_source,
                funding_time_ago=self._format_time_ago(hours_since_funding),
                is_new_freshie=False,
                is_old_freshie=False,
                amount_sol=amount_sol,
                market_cap=market_cap,
                is_via_router=is_via_router,
                router_name=router_name,
                router_emoji=router_emoji,
            )

        # Check if low tx count (required for all freshie types)
        is_low_tx = wallet_tx_count <= self.max_tx_count

        # Check minimum market cap (filter out micro caps)
        if market_cap is not None and market_cap < settings.min_market_cap:
            return FreshieClassification(
                is_valid_alert=False,
                primary_channel=None,
                all_channels=[],
                wallet_age_hours=hours_since_funding,
                wallet_tx_count=wallet_tx_count,
                funding_source=funding_source,
                funding_time_ago=self._format_time_ago(hours_since_funding),
                is_new_freshie=False,
                is_old_freshie=False,
                amount_sol=amount_sol,
                market_cap=market_cap,
                is_via_router=is_via_router,
                router_name=router_name,
                router_emoji=router_emoji,
            )

        if not is_low_tx:
            # Not a freshie at all
            return FreshieClassification(
                is_valid_alert=False,
                primary_channel=None,
                all_channels=[],
                wallet_age_hours=hours_since_funding,
                wallet_tx_count=wallet_tx_count,
                funding_source=funding_source,
                funding_time_ago=self._format_time_ago(hours_since_funding),
                is_new_freshie=False,
                is_old_freshie=False,
                amount_sol=amount_sol,
                market_cap=market_cap,
                is_via_router=is_via_router,
                router_name=router_name,
                router_emoji=router_emoji,
            )
        
        # Determine if new freshie (<24h) or old freshie (≥24h but <60 days)
        is_new_freshie = hours_since_funding < self.fresh_hours_threshold
        max_old_freshie_hours = 60 * 24  # 60 days max for Old Freshies
        is_old_freshie = (
            hours_since_funding >= self.fresh_hours_threshold and 
            hours_since_funding < max_old_freshie_hours
        )
        
        channels = []
        primary_channel = None
        
        if is_old_freshie:
            # Old Freshies - funded ≥24h ago but <60 days, low tx count
            channels.append(FreshieChannel.OLD_FRESHIES)
            primary_channel = FreshieChannel.OLD_FRESHIES
            
        elif is_new_freshie:
            # New freshie categories (funded <24h ago)
            
            # TG Freshies - via bot router (highest priority)
            if is_via_router:
                channels.append(FreshieChannel.TG_FRESHIES)
                primary_channel = FreshieChannel.TG_FRESHIES
            
            # Low MC Big Freshies - >5 SOL, MC ≤5M
            if market_cap and amount_sol >= self.low_mc_big_sol and market_cap <= self.low_mc_big_cap:
                channels.append(FreshieChannel.LOW_MC_BIG)
                if not primary_channel:
                    primary_channel = FreshieChannel.LOW_MC_BIG
            
            # Big Freshies - >7 SOL
            if amount_sol >= self.big_freshie_sol:
                channels.append(FreshieChannel.BIG_FRESHIES)
                if not primary_channel:
                    primary_channel = FreshieChannel.BIG_FRESHIES
            
            # Low MC Freshies - MC ≤500k
            if market_cap and market_cap <= self.low_mc_cap:
                channels.append(FreshieChannel.LOW_MC)
                if not primary_channel:
                    primary_channel = FreshieChannel.LOW_MC
            
            # Base Freshies - >0.47 SOL (always if new freshie)
            if amount_sol >= self.min_freshie_sol:
                channels.append(FreshieChannel.FRESHIES)
                if not primary_channel:
                    primary_channel = FreshieChannel.FRESHIES
        
        is_valid = len(channels) > 0
        
        return FreshieClassification(
            is_valid_alert=is_valid,
            primary_channel=primary_channel,
            all_channels=channels,
            wallet_age_hours=hours_since_funding,
            wallet_tx_count=wallet_tx_count,
            funding_source=funding_source,
            funding_time_ago=self._format_time_ago(hours_since_funding),
            is_new_freshie=is_new_freshie,
            is_old_freshie=is_old_freshie,
            amount_sol=amount_sol,
            market_cap=market_cap,
            is_via_router=is_via_router,
            router_name=router_name,
            router_emoji=router_emoji,
        )
    
    def _format_time_ago(self, hours: int) -> str:
        """Format hours into readable time ago."""
        if hours < 1:
            return "&lt;1h"  # Escaped for HTML
        elif hours < 24:
            return f"{hours}h"
        else:
            days = hours // 24
            return f"{days}d"
    
    def classify_dormant(
        self,
        wallet_address: str,
        amount_sol: float,
        market_cap: Optional[float],
        days_since_last_activity: int,
        program_ids: List[str],
        launchpad_name: Optional[str] = None,
        launchpad_emoji: str = "",
    ) -> DormantClassification:
        """Classify a purchase as dormant wallet activity.
        
        Subtypes:
        - Big Dormants: ≥7 SOL, 4+ days inactive
        - Semi-Dormants: ≥1 SOL, low MC (≤500k), 3+ days inactive  
        - Dormants: ≥3 SOL, 4+ days inactive
        """
        from config import settings
        
        # Check router
        router_name = None
        router_emoji = ""
        is_via_router = False
        for pid in program_ids:
            if pid in TG_ROUTERS:
                router_name, router_emoji = TG_ROUTERS[pid]
                is_via_router = True
                break
        
        # Thresholds
        SEMI_DORMANT_MIN_DAYS = 3
        BIG_DORMANT_MIN_SOL = 7.0
        SEMI_DORMANT_LOW_MC = 500_000
        
        # Classification flags
        is_semi_dormant = days_since_last_activity >= SEMI_DORMANT_MIN_DAYS and days_since_last_activity < settings.dormant_min_days
        is_old_dormant = days_since_last_activity >= settings.dormant_min_days
        is_big_dormant = amount_sol >= BIG_DORMANT_MIN_SOL and days_since_last_activity >= settings.dormant_min_days
        
        # Low MC check for semi-dormants
        is_low_mc = market_cap is not None and market_cap <= SEMI_DORMANT_LOW_MC
        
        # Determine dormant type
        dormant_type = None
        is_valid = False
        
        if is_big_dormant:
            dormant_type = DormantType.BIG_DORMANTS
            is_valid = True
        elif is_semi_dormant and is_low_mc and amount_sol >= 1.0:
            dormant_type = DormantType.SEMI_DORMANTS
            is_valid = True
        elif is_old_dormant and amount_sol >= settings.min_dormant_sol:
            dormant_type = DormantType.DORMANTS
            is_valid = True
        
        # Determine emoji
        if is_old_dormant or is_big_dormant:
            dormant_emoji = "👴🏻"
        elif is_semi_dormant:
            dormant_emoji = "🕰️"
        else:
            dormant_emoji = ""
        
        return DormantClassification(
            is_valid_alert=is_valid,
            dormant_type=dormant_type,
            wallet_address=wallet_address,
            last_active_days=days_since_last_activity,
            last_active_str=f"{days_since_last_activity}d",
            is_semi_dormant=is_semi_dormant,
            is_old_dormant=is_old_dormant,
            is_big_dormant=is_big_dormant,
            dormant_emoji=dormant_emoji,
            amount_sol=amount_sol,
            market_cap=market_cap,
            is_via_router=is_via_router,
            router_name=router_name,
            router_emoji=router_emoji,
            launchpad_name=launchpad_name,
            launchpad_emoji=launchpad_emoji,
        )
    
    def get_channel_title(self, channel: FreshieChannel) -> str:
        """Get display title for channel (used in alert header)."""
        titles = {
            FreshieChannel.FRESHIES: "Freshies",
            FreshieChannel.TG_FRESHIES: "TG Freshies",
            FreshieChannel.OLD_FRESHIES: "Old Freshies",
            FreshieChannel.BIG_FRESHIES: "Big Freshies",
            FreshieChannel.LOW_MC_BIG: "Low MC Big Freshies",
            FreshieChannel.LOW_MC: "Low MC Freshies",
        }
        return titles.get(channel, "Freshies")


# Singleton
_channel_router: FreshieChannelRouter | None = None


def get_channel_router() -> FreshieChannelRouter:
    """Get the singleton channel router."""
    global _channel_router
    if _channel_router is None:
        _channel_router = FreshieChannelRouter()
    return _channel_router
