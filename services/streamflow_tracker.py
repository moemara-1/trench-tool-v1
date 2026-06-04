"""
Trench Tool V1 - Streamflow Lock Tracker
Monitors token locks on Streamflow.finance.
Token locks are typically a sign of a more serious project.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)

# Streamflow program IDs (verified from official docs)
# Main vesting/streaming program - this is the on-chain program
STREAMFLOW_PROGRAM = "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m"

# Additional Streamflow-related programs that may appear in lock transactions
# The vesting program creates PDAs and interacts with these
STREAMFLOW_PROGRAMS = {
    "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m",  # Main vesting program
}


@dataclass
class StreamflowLock:
    """A detected Streamflow lock event."""
    token_address: str
    lock_amount: float
    lock_duration_days: int
    recipient: str
    detected_at: datetime


class StreamflowTracker:
    """
    Monitors Streamflow for token locks.
    
    Streamflow is a token vesting/lock platform. When a dev locks
    tokens via Streamflow, it's a bullish signal indicating:
    - Long-term commitment
    - Reduced sell pressure
    - More serious project
    """
    
    def __init__(self):
        self._locks: Dict[str, List[StreamflowLock]] = {}
        self._alerted_tokens: set[str] = set()
        self._alerts_sent = 0
    
    def is_streamflow_lock(self, program_ids: list) -> bool:
        """Check if transaction involves Streamflow locking."""
        is_lock = any(pid in STREAMFLOW_PROGRAMS for pid in program_ids)
        if is_lock:
            logger.info(f"🔒 [Streamflow] LOCK TX DETECTED: programs={[p[:8]+'...' for p in program_ids[:3]]}")
        return is_lock
    
    def parse_lock_from_tx(self, tx_data: dict, token_address: str) -> Optional[StreamflowLock]:
        """
        Parse lock details from a Streamflow transaction.
        Returns StreamflowLock if successfully parsed.
        """
        logger.debug(f"[Streamflow] PARSING lock for token={token_address[:12]}...")
        try:
            meta = tx_data.get("meta", {})
            
            # Get token balance changes to estimate lock amount
            post_tokens = meta.get("postTokenBalances", [])
            pre_tokens = meta.get("preTokenBalances", [])
            
            lock_amount = 0.0
            for post in post_tokens:
                if post.get("mint") == token_address:
                    post_amount = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                    pre_amount = 0
                    for pre in pre_tokens:
                        if pre.get("mint") == token_address:
                            pre_amount = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                            break
                    lock_amount = abs(post_amount - pre_amount)
                    break
            
            if lock_amount == 0:
                logger.debug(f"[Streamflow] NO LOCK: Zero balance change for token={token_address[:12]}...")
                return None
            
            # Create lock record (duration would need to be parsed from instruction data)
            lock = StreamflowLock(
                token_address=token_address,
                lock_amount=lock_amount,
                lock_duration_days=0,  # Would need instruction parsing
                recipient="",
                detected_at=datetime.utcnow(),
            )
            
            if token_address not in self._locks:
                self._locks[token_address] = []
            self._locks[token_address].append(lock)
            
            logger.info(f"🔒 [Streamflow] LOCK PARSED: token={token_address[:12]}... | amount={lock_amount:,.0f} | total_locks={len(self._locks)}")
            return lock
            
        except Exception as e:
            logger.error(f"[Streamflow] Error parsing lock: {e}")
            return None
    
    async def format_streamflow_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        lock_amount: float,
        market_cap_str: str = "?",
        coin_age_str: str = "?",
    ) -> str:
        """
        Format a Streamflow lock alert.
        
        🔒 SOL Streamflow Lock
        $TICKER TokenName | 1M tokens locked
        MC: $500K | CA: 2d
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        # Format lock amount
        if lock_amount >= 1_000_000:
            amount_str = f"{lock_amount / 1_000_000:.1f}M"
        elif lock_amount >= 1_000:
            amount_str = f"{lock_amount / 1_000:.1f}K"
        else:
            amount_str = f"{lock_amount:.0f}"
        
        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address
        
        message = f"""🔒 SOL Streamflow Lock
${ticker} {token_name} | {amount_str} tokens locked
MC: {market_cap_str} | CA: {coin_age_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://dexscreener.com/solana/{contract_address}">XX</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1

    def should_alert_token(self, token_address: str) -> bool:
        """Return true when this lock token has not already alerted."""
        return token_address not in self._alerted_tokens

    def mark_alerted(self, token_address: str):
        """Mark a token as alerted to prevent repeat lock spam."""
        self._alerted_tokens.add(token_address)
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "tokens_with_locks": len(self._locks),
            "total_locks": sum(len(locks) for locks in self._locks.values()),
            "alerted_tokens": len(self._alerted_tokens),
            "alerts_sent": self._alerts_sent,
        }


# Singleton
_streamflow_tracker: StreamflowTracker | None = None


def get_streamflow_tracker() -> StreamflowTracker:
    """Get the singleton Streamflow tracker."""
    global _streamflow_tracker
    if _streamflow_tracker is None:
        _streamflow_tracker = StreamflowTracker()
    return _streamflow_tracker
