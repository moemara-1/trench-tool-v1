"""
Trench Tool V1 - Transaction Filter
Applies filters to transactions and generates indicator emojis.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from config import settings
from .launchpad_detector import detect_launchpad, get_launchpad_emoji
from .router_detector import detect_router, get_router_emoji


@dataclass
class TransactionIndicators:
    """All indicators for a transaction."""
    # Value indicators
    is_whale: bool = False        # 🐳 > 15 SOL
    is_dolphin: bool = False      # 🐬 > 5 SOL
    is_first_mention: bool = False  # ⭐️ First time we see this token
    
    # Launchpad
    launchpad_emoji: str = ""
    launchpad_name: str = ""
    
    # Router/Bot
    router_emoji: str = ""
    router_name: str = ""
    
    # Wallet type
    wallet_emoji: str = ""  # 👶🏻 fresh, ⏳ dormant
    
    def get_emoji_string(self) -> str:
        """Build the full emoji indicator string."""
        emojis = []
        
        # First mention star
        if self.is_first_mention:
            emojis.append("⭐️")
        
        # Value indicators
        if self.is_whale:
            emojis.append("🐳")
        elif self.is_dolphin:
            emojis.append("🐬")
        
        # Wallet type
        if self.wallet_emoji:
            emojis.append(self.wallet_emoji)
        
        # Launchpad
        if self.launchpad_emoji:
            emojis.append(self.launchpad_emoji)
        
        # Router
        if self.router_emoji:
            emojis.append(self.router_emoji)
        
        return " ".join(emojis)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "is_whale": self.is_whale,
            "is_dolphin": self.is_dolphin,
            "is_first_mention": self.is_first_mention,
            "launchpad_emoji": self.launchpad_emoji,
            "launchpad_name": self.launchpad_name,
            "router_emoji": self.router_emoji,
            "router_name": self.router_name,
            "wallet_emoji": self.wallet_emoji,
            "emoji_string": self.get_emoji_string(),
        }


class TransactionFilter:
    """Applies filters and generates indicators for transactions."""
    
    def __init__(self):
        self._seen_tokens: set[str] = set()  # Track first mentions
    
    def analyze_transaction(
        self,
        amount_sol: float,
        program_ids: list[str],
        token_address: str,
        wallet_type: str = "active",
    ) -> TransactionIndicators:
        """
        Analyze a transaction and return all indicators.
        
        Args:
            amount_sol: Transaction amount in SOL
            program_ids: List of program IDs involved
            token_address: Token contract address
            wallet_type: Type of wallet (fresh, dormant, active)
            
        Returns:
            TransactionIndicators with all applicable indicators
        """
        indicators = TransactionIndicators()
        
        # Value indicators
        indicators.is_whale = amount_sol >= settings.whale_threshold_sol
        indicators.is_dolphin = (
            amount_sol >= settings.dolphin_threshold_sol 
            and not indicators.is_whale
        )
        
        # First mention check
        if token_address not in self._seen_tokens:
            indicators.is_first_mention = True
            self._seen_tokens.add(token_address)
        
        # Launchpad detection
        launchpad = detect_launchpad(program_ids)
        if launchpad:
            indicators.launchpad_emoji = launchpad.emoji
            indicators.launchpad_name = launchpad.name
        
        # Router detection
        router = detect_router(program_ids)
        if router:
            indicators.router_emoji = router.emoji
            indicators.router_name = router.name
        
        # Wallet type emoji
        if wallet_type == "fresh":
            indicators.wallet_emoji = "👶🏻"
        elif wallet_type == "dormant":
            indicators.wallet_emoji = "⏳"
        
        return indicators
    
    def should_alert(
        self,
        amount_sol: float,
        wallet_type: str,
        indicators: TransactionIndicators,
    ) -> bool:
        """
        Determine if this transaction should trigger an alert.
        
        High-priority alerts:
        - Fresh wallet purchases
        - Whale transactions
        - Dormant wallets waking up
        - First mentions
        """
        # Always alert on fresh wallet purchases above minimum
        if wallet_type == "fresh" and amount_sol >= settings.min_transaction_sol:
            return True
        
        # Alert on whale transactions
        if indicators.is_whale:
            return True
        
        # Alert on dormant wallet activity
        if wallet_type == "dormant":
            return True
        
        # Alert on first mentions with significant volume
        if indicators.is_first_mention and amount_sol >= settings.dolphin_threshold_sol:
            return True
        
        return False
    
    def get_alert_priority(
        self,
        amount_sol: float,
        wallet_type: str,
        indicators: TransactionIndicators,
    ) -> str:
        """
        Determine alert priority level.
        
        Returns: "critical", "high", "medium", or "low"
        """
        # Critical: Whale fresh wallet purchase
        if wallet_type == "fresh" and indicators.is_whale:
            return "critical"
        
        # Critical: First mention whale
        if indicators.is_first_mention and indicators.is_whale:
            return "critical"
        
        # High: Any whale or fresh wallet dolphin
        if indicators.is_whale:
            return "high"
        if wallet_type == "fresh" and indicators.is_dolphin:
            return "high"
        
        # Medium: Fresh wallet purchases, dormant activity
        if wallet_type in ("fresh", "dormant"):
            return "medium"
        
        # Low: Everything else
        return "low"


# Singleton filter instance
_filter_instance: TransactionFilter | None = None


def get_transaction_filter() -> TransactionFilter:
    """Get the singleton transaction filter."""
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = TransactionFilter()
    return _filter_instance
