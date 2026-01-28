"""
BSC Transaction Tracker
Tracks per-token statistics for fresh and dormant wallets.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Set, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TokenStats:
    """Statistics for a single token."""
    token_address: str
    fresh_buys: int = 0
    fresh_full_sells: int = 0
    fresh_partial_sells: int = 0
    dormant_buys: int = 0
    
    # Track wallets to avoid double-counting
    fresh_buyers: Set[str] = field(default_factory=set)
    dormant_buyers: Set[str] = field(default_factory=set)
    
    # Track fresh sellers
    fresh_full_sellers: Set[str] = field(default_factory=set)
    fresh_partial_sellers: Set[str] = field(default_factory=set)
    
    # First mention tracking
    first_mention_time: Optional[datetime] = None
    is_first_mention: bool = True
    
    # Counters for specific channels
    counter_freshies: int = 0
    counter_big_freshies: int = 0
    counter_lowmc: int = 0
    counter_dormants: int = 0
    counter_semidormants: int = 0


class BSCTxTracker:
    """Tracks transactions per token for BBB-style stats."""
    
    def __init__(self):
        self._tokens: Dict[str, TokenStats] = {}
        self._seen_signatures: Set[str] = set()
    
    def _get_or_create(self, token_address: str) -> TokenStats:
        """Get or create token stats."""
        if token_address not in self._tokens:
            self._tokens[token_address] = TokenStats(
                token_address=token_address,
                first_mention_time=datetime.utcnow(),
            )
        return self._tokens[token_address]
    
    def is_first_mention(self, token_address: str) -> bool:
        """Check if this is the first mention of a token."""
        if token_address not in self._tokens:
            return True
        return self._tokens[token_address].is_first_mention
    
    def record_fresh_buy(
        self,
        token_address: str,
        wallet: str,
        tx_hash: str,
    ) -> TokenStats:
        """Record a fresh wallet buy."""
        if tx_hash in self._seen_signatures:
            return self._get_or_create(token_address)
        
        self._seen_signatures.add(tx_hash)
        stats = self._get_or_create(token_address)
        
        # Mark no longer first mention
        stats.is_first_mention = False
        
        # Only count if new buyer
        if wallet not in stats.fresh_buyers:
            stats.fresh_buyers.add(wallet)
            stats.fresh_buys += 1
        
        return stats
    
    def record_dormant_buy(
        self,
        token_address: str,
        wallet: str,
        tx_hash: str,
    ) -> TokenStats:
        """Record a dormant wallet buy."""
        if tx_hash in self._seen_signatures:
            return self._get_or_create(token_address)
        
        self._seen_signatures.add(tx_hash)
        stats = self._get_or_create(token_address)
        
        # Mark no longer first mention
        stats.is_first_mention = False
        
        # Only count if new buyer
        if wallet not in stats.dormant_buyers:
            stats.dormant_buyers.add(wallet)
            stats.dormant_buys += 1
        
        return stats
    
    def record_fresh_sell(
        self,
        token_address: str,
        wallet: str,
        is_full_sell: bool,
        tx_hash: str,
    ) -> TokenStats:
        """Record a fresh wallet sell."""
        if tx_hash in self._seen_signatures:
            return self._get_or_create(token_address)
        
        self._seen_signatures.add(tx_hash)
        stats = self._get_or_create(token_address)
        
        if is_full_sell:
            if wallet not in stats.fresh_full_sellers:
                stats.fresh_full_sellers.add(wallet)
                stats.fresh_full_sells += 1
        else:
            if wallet not in stats.fresh_partial_sellers:
                stats.fresh_partial_sellers.add(wallet)
                stats.fresh_partial_sells += 1
        
        return stats
    
    def get_stats(self, token_address: str) -> TokenStats:
        """Get statistics for a token."""
        return self._get_or_create(token_address)
    
    def increment_channel_counter(
        self,
        token_address: str,
        channel: str,
    ) -> int:
        """Increment and return counter for a specific channel."""
        stats = self._get_or_create(token_address)
        
        if channel == "freshies":
            stats.counter_freshies += 1
            return stats.counter_freshies
        elif channel == "big_freshies":
            stats.counter_big_freshies += 1
            return stats.counter_big_freshies
        elif channel == "lowmc":
            stats.counter_lowmc += 1
            return stats.counter_lowmc
        elif channel == "dormants":
            stats.counter_dormants += 1
            return stats.counter_dormants
        elif channel == "semidormants":
            stats.counter_semidormants += 1
            return stats.counter_semidormants
        
        return 1
    
    def cleanup_old_signatures(self, max_size: int = 10000):
        """Clean up old signatures to prevent memory bloat."""
        if len(self._seen_signatures) > max_size:
            # Keep only the most recent half
            self._seen_signatures = set(list(self._seen_signatures)[-max_size // 2:])


# Singleton
_tracker: Optional[BSCTxTracker] = None


def get_bsc_tx_tracker() -> BSCTxTracker:
    """Get singleton transaction tracker."""
    global _tracker
    if _tracker is None:
        _tracker = BSCTxTracker()
    return _tracker
