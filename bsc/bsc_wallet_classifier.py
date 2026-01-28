"""
BSC Wallet Classifier
Classifies wallets as fresh, dormant, or semi-dormant based on activity.
Matches Solana freshie criteria: funded <24h ago + low tx count
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime

from bsc.bsc_config import bsc_settings
from bsc.bsc_api_clients import get_bscscan_client, BSCWalletInfo

logger = logging.getLogger(__name__)


class WalletType(Enum):
    """Wallet classification types."""
    FRESH = "fresh"           # Funded <24h ago, low tx count
    OLD_FRESH = "old_fresh"   # Funded 24h-60d ago, low tx count
    SEMI_DORMANT = "semi_dormant"
    DORMANT = "dormant"
    OLD_DORMANT = "old_dormant"
    NORMAL = "normal"


@dataclass
class WalletClassification:
    """Result of wallet classification."""
    wallet_address: str
    wallet_type: WalletType
    is_fresh: bool = False      # Funded <24h, low tx
    is_old_fresh: bool = False  # Funded 24h-60d, low tx
    is_dormant: bool = False
    is_semi_dormant: bool = False
    is_old_dormant: bool = False
    
    # Details
    age_days: int = 0
    tx_count: int = 0
    last_activity_days: int = 0
    funding_source: str = "Unknown"
    funding_time_ago: str = "?"
    hours_since_funding: int = 0
    
    # Emojis
    dormant_emoji: str = ""
    
    @property
    def is_valid_freshie(self) -> bool:
        """Check if wallet qualifies for freshies alert."""
        return self.is_fresh or self.is_old_fresh
    
    @property
    def is_valid_dormant(self) -> bool:
        """Check if wallet qualifies for dormants alert."""
        return self.is_dormant or self.is_old_dormant


class BSCWalletClassifier:
    """Classifies BSC wallets based on activity patterns.
    
    Freshie criteria (matching Solana):
    - New Freshie: funded <24h ago + tx count ≤50
    - Old Freshie: funded 24h-60d ago + tx count ≤50
    
    Dormant criteria:
    - Semi-Dormant: 3-6 days since last activity
    - Dormant: 7+ days since last activity
    - Old Dormant: 12+ days since last activity
    """
    
    # Thresholds matching Solana
    FRESH_HOURS_THRESHOLD = 24       # <24h = new freshie
    OLD_FRESH_MAX_HOURS = 60 * 24    # 60 days max for old freshie
    MAX_TX_COUNT = 50                # Max tx for freshie
    
    def __init__(self):
        self.bscscan = get_bscscan_client()
    
    async def classify(self, wallet_address: str) -> WalletClassification:
        """Classify a wallet based on its activity."""
        
        # Get wallet info from BscScan
        wallet_info = await self.bscscan.get_wallet_info(wallet_address)
        
        # Calculate hours since funding
        hours_since_funding = 0
        if wallet_info.funding_time:
            delta = datetime.utcnow() - wallet_info.funding_time
            hours_since_funding = int(delta.total_seconds() / 3600)
        
        # Determine classification
        wallet_type = WalletType.NORMAL
        is_fresh = False
        is_old_fresh = False
        is_dormant = False
        is_semi_dormant = False
        is_old_dormant = False
        dormant_emoji = ""
        
        # Check FRESH criteria (funding-based like Solana)
        is_low_tx = wallet_info.tx_count <= self.MAX_TX_COUNT
        
        if is_low_tx and hours_since_funding > 0:
            if hours_since_funding < self.FRESH_HOURS_THRESHOLD:
                # New freshie - funded <24h ago
                wallet_type = WalletType.FRESH
                is_fresh = True
            elif hours_since_funding < self.OLD_FRESH_MAX_HOURS:
                # Old freshie - funded 24h-60d ago
                wallet_type = WalletType.OLD_FRESH
                is_old_fresh = True
        
        # If not a freshie, check DORMANT criteria (based on last activity)
        if wallet_type == WalletType.NORMAL:
            if wallet_info.last_activity_days >= bsc_settings.dormant_old_days:
                # Old dormant (12+ days)
                wallet_type = WalletType.OLD_DORMANT
                is_dormant = True
                is_old_dormant = True
                dormant_emoji = "👴🏻"
            
            elif wallet_info.last_activity_days >= bsc_settings.dormant_min_days:
                # Regular dormant (7+ days)
                wallet_type = WalletType.DORMANT
                is_dormant = True
                dormant_emoji = "🕰️"
            
            elif (wallet_info.last_activity_days >= bsc_settings.semidormant_min_days and
                  wallet_info.last_activity_days <= bsc_settings.semidormant_max_days):
                # Semi-dormant (3-6 days)
                wallet_type = WalletType.SEMI_DORMANT
                is_semi_dormant = True
        
        return WalletClassification(
            wallet_address=wallet_address,
            wallet_type=wallet_type,
            is_fresh=is_fresh,
            is_old_fresh=is_old_fresh,
            is_dormant=is_dormant,
            is_semi_dormant=is_semi_dormant,
            is_old_dormant=is_old_dormant,
            age_days=wallet_info.age_days,
            tx_count=wallet_info.tx_count,
            last_activity_days=wallet_info.last_activity_days,
            funding_source=wallet_info.funding_source,
            funding_time_ago=wallet_info.funding_time_ago,
            hours_since_funding=hours_since_funding,
            dormant_emoji=dormant_emoji,
        )


# Singleton
_classifier: Optional[BSCWalletClassifier] = None


def get_bsc_wallet_classifier() -> BSCWalletClassifier:
    """Get singleton wallet classifier."""
    global _classifier
    if _classifier is None:
        _classifier = BSCWalletClassifier()
    return _classifier

