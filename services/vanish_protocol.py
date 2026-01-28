"""
Trench Tool V1 - Vanish Protocol Tracker
Monitors purchases made via Vanish Protocol (privacy trading).
Vanish buys indicate smart money using privacy features.
"""

import logging
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


# Vanish Protocol program IDs (Vanish uses multiple programs)
VANISH_PROGRAM_IDS = {
    "vanish1111111111111111111111111111111111111",  # Main Vanish
    "VANish2222222222222222222222222222222222222",  # Vanish Router
}

# Known launchpad programs for emoji classification
LAUNCHPAD_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": ("pump.fun", "💊"),
    "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG": ("Moonshot", "🌙"),
    "BondJt3nh3SQq1MJfWtUkPKoZpP9yPG9jE7BshGbEbj5": ("Bonk", "🐕"),
    "RAYugarpBb6qJZsXMbJ7CZ9nVCvKkD95j2mCqoMCZC8": ("Raydium LP", "🔮"),
    "SugarR1q7RxWFFTeSMVvjNGxj2GVVnvYQqkXMuzbvLT": ("Sugar", "🍭"),
}

# DEX programs for pool type detection
DEX_PROGRAMS = {
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": ("Orca", "🐋"),
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": ("Raydium", "®️"),
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": ("Raydium CLMM", "®️💧"),
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": ("Meteora", "☄️"),
}


class VanishType(str, Enum):
    """Vanish buy subtypes."""
    VANISH_BUYS = "vanish_buys"           # ≥1 SOL via Vanish
    VANISH_BIG_BUYS = "vanish_big_buys"   # ≥7 SOL via Vanish


@dataclass
class VanishClassification:
    """Classification result for a Vanish protocol purchase."""
    is_valid_alert: bool
    vanish_type: Optional[VanishType]
    
    # Purchase info
    amount_sol: float
    market_cap: Optional[float]
    
    # Launchpad/DEX info
    launchpad_name: Optional[str]
    launchpad_emoji: str
    dex_name: Optional[str]
    dex_emoji: str
    
    # Indicators
    is_first_mention: bool
    is_whale: bool  # ≥10 SOL


class VanishProtocolTracker:
    """
    Tracks purchases made via Vanish Protocol.
    
    Vanish Protocol is a privacy trading solution that shields
    transactions from public view. Wallets using Vanish are often
    sophisticated traders who want to hide their activity.
    """
    
    def __init__(self):
        self._vanish_buys: Dict[str, int] = {}  # token -> count
        self._seen_tokens: set = set()
        self._alerts_sent = 0
        self._big_alerts_sent = 0
    
    def is_vanish_transaction(self, program_ids: list) -> bool:
        """Check if a transaction uses Vanish Protocol."""
        for pid in program_ids:
            if pid in VANISH_PROGRAM_IDS:
                return True
        return False
    
    def detect_launchpad(self, program_ids: list) -> tuple:
        """Detect launchpad from program IDs."""
        for pid in program_ids:
            if pid in LAUNCHPAD_PROGRAMS:
                return LAUNCHPAD_PROGRAMS[pid]
        return (None, "")
    
    def detect_dex(self, program_ids: list) -> tuple:
        """Detect DEX/pool type from program IDs."""
        for pid in program_ids:
            if pid in DEX_PROGRAMS:
                return DEX_PROGRAMS[pid]
        return (None, "")
    
    def classify_vanish(
        self,
        token_address: str,
        amount_sol: float,
        market_cap: Optional[float],
        program_ids: list,
    ) -> VanishClassification:
        """Classify a Vanish protocol purchase."""
        
        # Check thresholds
        VANISH_MIN_SOL = 1.0
        VANISH_BIG_MIN_SOL = 7.0
        WHALE_THRESHOLD = 10.0
        
        # Determine type
        vanish_type = None
        is_valid = False
        
        if amount_sol >= VANISH_BIG_MIN_SOL:
            vanish_type = VanishType.VANISH_BIG_BUYS
            is_valid = True
        elif amount_sol >= VANISH_MIN_SOL:
            vanish_type = VanishType.VANISH_BUYS
            is_valid = True
        
        # Detect launchpad/DEX
        launchpad_name, launchpad_emoji = self.detect_launchpad(program_ids)
        dex_name, dex_emoji = self.detect_dex(program_ids)
        
        # First mention
        is_first = token_address not in self._seen_tokens
        
        return VanishClassification(
            is_valid_alert=is_valid,
            vanish_type=vanish_type,
            amount_sol=amount_sol,
            market_cap=market_cap,
            launchpad_name=launchpad_name,
            launchpad_emoji=launchpad_emoji,
            dex_name=dex_name,
            dex_emoji=dex_emoji,
            is_first_mention=is_first,
            is_whale=amount_sol >= WHALE_THRESHOLD,
        )
    
    async def format_vanish_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        amount_sol: float,
        market_cap_str: str,
        coin_age_str: str,
        vanish_type: VanishType,
        count: int = 1,
        launchpad_emoji: str = "",
        dex_emoji: str = "",
        is_first_mention: bool = False,
        is_whale: bool = False,
    ) -> str:
        """
        Format a Vanish Buys alert in BBB style:
        
        🐍 SOL Vanish [BBB]
        [41] DETECTIVE Just can't prove it 1.82
        14GPMP...pump
        MC: $360.5K | CA: 121d
        AX | PH | BL | TJ | BA | MA | MP | PD | BU | PF
        """
        # Determine header
        if vanish_type == VanishType.VANISH_BIG_BUYS:
            header = "SOL Vanish Big Buys"
        else:
            header = "SOL Vanish"
        
        # Build emoji indicators
        emojis = []
        if is_first_mention:
            emojis.append("⭐️")
        if is_whale:
            emojis.append("🐳")
        if launchpad_emoji:
            emojis.append(launchpad_emoji)
        if dex_emoji:
            emojis.append(dex_emoji)
        
        emoji_str = " ".join(emojis) + (" " if emojis else "")
        
        # Get pair address for Axiom link
        from services.api_clients import get_token_fetcher
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address
        
        message = f"""🐍 {header}
[{count}] {emoji_str}${ticker} {token_name} {amount_sol:.2f}
<code>{contract_address}</code>
MC: {market_cap_str} | CA: {coin_age_str}
<a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    def track_vanish_buy(self, token_address: str) -> int:
        """Track a Vanish buy and return the count."""
        if token_address not in self._vanish_buys:
            self._vanish_buys[token_address] = 0
        self._vanish_buys[token_address] += 1
        
        if token_address not in self._seen_tokens:
            self._seen_tokens.add(token_address)
        
        return self._vanish_buys[token_address]
    
    def increment_alerts(self, is_big: bool = False):
        """Increment alert counters."""
        self._alerts_sent += 1
        if is_big:
            self._big_alerts_sent += 1
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "vanish_buys_tracked": sum(self._vanish_buys.values()),
            "unique_tokens": len(self._seen_tokens),
            "alerts_sent": self._alerts_sent,
            "big_alerts_sent": self._big_alerts_sent,
        }


# Singleton
_vanish_tracker: VanishProtocolTracker | None = None


def get_vanish_tracker() -> VanishProtocolTracker:
    """Get the singleton Vanish protocol tracker."""
    global _vanish_tracker
    if _vanish_tracker is None:
        _vanish_tracker = VanishProtocolTracker()
    return _vanish_tracker
