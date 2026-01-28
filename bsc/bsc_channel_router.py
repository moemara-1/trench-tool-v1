"""
BSC Channel Router
Routes BSC alerts to appropriate Telegram topics based on classification.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from bsc.bsc_config import bsc_settings
from bsc.bsc_wallet_classifier import WalletClassification, WalletType

logger = logging.getLogger(__name__)


class BSCChannel(Enum):
    """BSC alert channels."""
    FRESHIES = "freshies"
    BIG_FRESHIES = "big_freshies"
    LOW_MC_FRESHIES = "lowmc"
    DORMANTS = "dormants"
    SEMI_DORMANTS = "semidormants"


@dataclass
class BSCChannelClassification:
    """Result of channel classification."""
    channel: BSCChannel
    topic_id: int
    is_valid_alert: bool
    
    # Emojis
    is_whale: bool = False
    is_dolphin: bool = False
    is_usdt: bool = False
    is_first_mention: bool = False
    launchpad_emoji: str = ""
    
    @property
    def channel_title(self) -> str:
        """Get display title for channel."""
        titles = {
            BSCChannel.FRESHIES: "Freshies",
            BSCChannel.BIG_FRESHIES: "Big Freshies",
            BSCChannel.LOW_MC_FRESHIES: "Low MC Freshies",
            BSCChannel.DORMANTS: "Dormants",
            BSCChannel.SEMI_DORMANTS: "Semi-Dormants",
        }
        return titles.get(self.channel, "Freshies")


# Launchpad detection
BSC_LAUNCHPADS = {
    # Four.meme - note: need actual contract address
    # "0x...": ("four.meme", "🍀"),
    
    # Meme Rush - note: need actual contract address
    # "0x...": ("meme_rush", "🚀🟡"),
}


class BSCChannelRouter:
    """Routes alerts to appropriate BSC Telegram topics."""
    
    def classify_freshies(
        self,
        wallet: WalletClassification,
        amount_bnb: float,
        amount_usd: float,
        market_cap: Optional[float],
        is_first_mention: bool,
        is_usdt_purchase: bool = False,
        launchpad: Optional[str] = None,
    ) -> BSCChannelClassification:
        """Classify a freshies alert."""
        
        # Check if valid freshie (new or old)
        if not (wallet.is_fresh or wallet.is_old_fresh):
            return BSCChannelClassification(
                channel=BSCChannel.FRESHIES,
                topic_id=0,
                is_valid_alert=False,
            )
        
        # Check minimum amount
        if amount_bnb < bsc_settings.min_transaction_bnb:
            return BSCChannelClassification(
                channel=BSCChannel.FRESHIES,
                topic_id=0,
                is_valid_alert=False,
            )
        
        # Check max market cap
        if market_cap and market_cap > bsc_settings.max_market_cap:
            return BSCChannelClassification(
                channel=BSCChannel.FRESHIES,
                topic_id=0,
                is_valid_alert=False,
            )
        
        # Determine channel
        channel = BSCChannel.FRESHIES
        topic_id = bsc_settings.telegram_bsc_freshies_topic_id
        
        # Low MC Freshies (MC <= 500K)
        if market_cap and market_cap <= bsc_settings.low_mc_threshold:
            channel = BSCChannel.LOW_MC_FRESHIES
            if bsc_settings.telegram_bsc_lowmc_topic_id > 0:
                topic_id = bsc_settings.telegram_bsc_lowmc_topic_id
        
        # Big Freshies (higher amounts - use separate topic if configured)
        # For now, big freshies go to same topic as freshies
        if bsc_settings.telegram_bsc_big_freshies_topic_id > 0:
            # Could add logic for "big" threshold
            pass
        
        # Whale/dolphin check
        is_whale = (amount_bnb >= bsc_settings.whale_threshold_bnb or 
                    amount_usd >= bsc_settings.whale_threshold_usd)
        is_dolphin = (not is_whale and 
                      (amount_bnb >= bsc_settings.dolphin_threshold_bnb or
                       amount_usd >= bsc_settings.dolphin_threshold_usd))
        
        # Launchpad emoji
        launchpad_emoji = ""
        if launchpad:
            if "four" in launchpad.lower():
                launchpad_emoji = "🍀"
            elif "meme_rush" in launchpad.lower() or "memerush" in launchpad.lower():
                launchpad_emoji = "🚀🟡"
        
        return BSCChannelClassification(
            channel=channel,
            topic_id=topic_id,
            is_valid_alert=True,
            is_whale=is_whale,
            is_dolphin=is_dolphin,
            is_usdt=is_usdt_purchase,
            is_first_mention=is_first_mention,
            launchpad_emoji=launchpad_emoji,
        )
    
    def classify_dormants(
        self,
        wallet: WalletClassification,
        amount_bnb: float,
        amount_usd: float,
        market_cap: Optional[float],
        is_first_mention: bool,
        is_usdt_purchase: bool = False,
        launchpad: Optional[str] = None,
    ) -> BSCChannelClassification:
        """Classify a dormants/semi-dormants alert."""
        
        # Check if dormant or semi-dormant
        if not (wallet.is_dormant or wallet.is_semi_dormant):
            return BSCChannelClassification(
                channel=BSCChannel.DORMANTS,
                topic_id=0,
                is_valid_alert=False,
            )
        
        # Determine channel and check thresholds
        if wallet.is_dormant or wallet.is_old_dormant:
            channel = BSCChannel.DORMANTS
            topic_id = bsc_settings.telegram_bsc_dormants_topic_id
            
            # Dormants require higher minimum
            if amount_bnb < bsc_settings.min_dormant_bnb:
                return BSCChannelClassification(
                    channel=channel,
                    topic_id=0,
                    is_valid_alert=False,
                )
        else:
            # Semi-dormant
            channel = BSCChannel.SEMI_DORMANTS
            topic_id = bsc_settings.telegram_bsc_semidormants_topic_id
            if topic_id == 0:
                topic_id = bsc_settings.telegram_bsc_dormants_topic_id  # Fall back
            
            # Semi-dormants use lower minimum
            if amount_bnb < bsc_settings.min_transaction_bnb:
                return BSCChannelClassification(
                    channel=channel,
                    topic_id=0,
                    is_valid_alert=False,
                )
        
        # Whale/dolphin check
        is_whale = (amount_bnb >= bsc_settings.whale_threshold_bnb or 
                    amount_usd >= bsc_settings.whale_threshold_usd)
        is_dolphin = (not is_whale and 
                      (amount_bnb >= bsc_settings.dolphin_threshold_bnb or
                       amount_usd >= bsc_settings.dolphin_threshold_usd))
        
        # Launchpad emoji
        launchpad_emoji = ""
        if launchpad:
            if "four" in launchpad.lower():
                launchpad_emoji = "🍀"
            elif "meme_rush" in launchpad.lower() or "memerush" in launchpad.lower():
                launchpad_emoji = "🚀🟡"
        
        return BSCChannelClassification(
            channel=channel,
            topic_id=topic_id,
            is_valid_alert=True,
            is_whale=is_whale,
            is_dolphin=is_dolphin,
            is_usdt=is_usdt_purchase,
            is_first_mention=is_first_mention,
            launchpad_emoji=launchpad_emoji,
        )


# Singleton
_router: Optional[BSCChannelRouter] = None


def get_bsc_channel_router() -> BSCChannelRouter:
    """Get singleton channel router."""
    global _router
    if _router is None:
        _router = BSCChannelRouter()
    return _router
