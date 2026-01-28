"""
Trench Tool V1 - Dev Held Tracker
Tracks tokens where the dev holds supply for an extended period.
On Solana, devs typically dump instantly, so holding is unusual and worth tracking.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class DevHolding:
    """Tracking data for a dev's holdings."""
    token_address: str
    dev_wallet: str
    initial_supply: float
    current_supply: float
    first_seen: datetime
    last_checked: datetime
    holding_hours: int
    has_sold: bool
    is_alerted: bool = False


class DevHeldTracker:
    """
    Tracks whether token devs hold their supply.
    
    Most Solana devs dump tokens immediately after launch.
    When a dev holds for an extended period (>1 hour), it's
    an unusual signal that may indicate:
    - More serious project
    - Confidence in the token
    - Strategic timing for sells
    """
    
    # Minimum hold time before alerting (hours)
    MIN_HOLD_HOURS = 1
    
    def __init__(self):
        # Track dev holdings: token -> DevHolding
        self._holdings: Dict[str, DevHolding] = {}
        self._alerts_sent = 0
    
    def record_dev_wallet(
        self,
        token_address: str,
        dev_wallet: str,
        initial_supply: float,
    ):
        """Record a new token's dev wallet and supply."""
        if token_address in self._holdings:
            logger.debug(f"[DevHeld] SKIP: Already tracking token={token_address[:12]}...")
            return  # Already tracking
        
        self._holdings[token_address] = DevHolding(
            token_address=token_address,
            dev_wallet=dev_wallet,
            initial_supply=initial_supply,
            current_supply=initial_supply,
            first_seen=datetime.utcnow(),
            last_checked=datetime.utcnow(),
            holding_hours=0,
            has_sold=False,
            is_alerted=False,
        )
        logger.info(f"💎 [DevHeld] TRACKING: wallet={dev_wallet[:12]}... | token={token_address[:12]}... | supply={initial_supply:,.0f} | total_tracked={len(self._holdings)}")
    
    def update_holding(
        self,
        token_address: str,
        current_supply: float,
    ) -> Optional[DevHolding]:
        """
        Update dev's current supply and check if still holding.
        Returns DevHolding if it's been held long enough for an alert.
        """
        if token_address not in self._holdings:
            logger.debug(f"[DevHeld] UPDATE SKIP: Not tracking token={token_address[:12]}...")
            return None
        
        holding = self._holdings[token_address]
        holding.last_checked = datetime.utcnow()
        holding.current_supply = current_supply
        
        # Check if dev has sold
        supply_pct = (current_supply / holding.initial_supply * 100) if holding.initial_supply > 0 else 0
        if current_supply < holding.initial_supply * 0.9:  # >10% sold
            holding.has_sold = True
            logger.info(f"💎 [DevHeld] DEV SOLD: token={token_address[:12]}... | supply_remaining={supply_pct:.1f}%")
            return None
        
        # Calculate holding time
        elapsed = datetime.utcnow() - holding.first_seen
        holding.holding_hours = int(elapsed.total_seconds() / 3600)
        
        # Check if exceeds threshold
        if holding.holding_hours >= self.MIN_HOLD_HOURS and not holding.has_sold:
            logger.info(f"💎 [DevHeld] HELD THRESHOLD MET: token={token_address[:12]}... | hours={holding.holding_hours}h | supply={supply_pct:.1f}%")
            return holding
        
        logger.debug(f"[DevHeld] UPDATE: token={token_address[:12]}... | hours={holding.holding_hours}h | threshold={self.MIN_HOLD_HOURS}h | supply={supply_pct:.1f}%")
        return None
    
    def check_should_alert(self, token_address: str) -> bool:
        """Check if we should send an alert for this token."""
        if token_address not in self._holdings:
            return False

        holding = self._holdings[token_address]
        return (
            holding.holding_hours >= self.MIN_HOLD_HOURS and
            not holding.has_sold and
            not holding.is_alerted
        )

    def format_dev_held_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        holding_hours: int,
        supply_pct: float,
        market_cap_str: str = "?",
    ) -> str:
        """
        Format a dev held alert.
        
        💎 SOL Dev Held
        $TICKER TokenName | Dev holding 2h
        Supply: 95% | MC: $500K
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        if holding_hours >= 24:
            time_str = f"{holding_hours // 24}d {holding_hours % 24}h"
        else:
            time_str = f"{holding_hours}h"
        
        # Get pair address for Axiom link (async call handled by solana_listener usually, 
        # but here we construct link directly or rely on listener. 
        # Note: calling async in format is tricky if not awaited. 
        # For simplicity, we'll use placeholder or standard logic from earlier)
        
        message = f"💎 SOL Dev Held\n${ticker} {token_name} | Dev holding {time_str}\nSupply: {supply_pct:.0f}% | MC: {market_cap_str}\n<code>{contract_address}</code>\n<a href=\"https://photon-sol.tinyastro.io/en/lp/{contract_address}\">PH</a> | <a href=\"https://axiom.trade/meme/{contract_address}?chain=sol\">AX</a> | <a href=\"https://t.me/paris_trojanbot?start={contract_address}\">TJ</a> | <a href=\"https://t.me/BananaGunSolana_bot?start={contract_address}\">BA</a> | <a href=\"https://trade.padre.gg/trade/solana/{contract_address}\">PR</a> | <a href=\"https://t.me/BloomSolana_bot?start={contract_address}\">BL</a> | <a href=\"https://t.me/MaestroSniperBot?start={contract_address}\">MA</a> | <a href=\"https://t.me/MaestroProBot?start={contract_address}\">MT</a> | <a href=\"https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}\">NE</a> | <a href=\"https://dexscreener.com/solana/{contract_address}\">XX</a> | <a href=\"https://pump.fun/{contract_address}\">PF</a>"
        
        return message.strip()
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        holding_count = sum(1 for h in self._holdings.values() if not h.has_sold)
        return {
            "tokens_tracked": len(self._holdings),
            "devs_holding": holding_count,
            "alerts_sent": self._alerts_sent,
        }
    
    def cleanup_sold(self):
        """Remove tokens where dev has completely sold."""
        to_remove = [
            addr for addr, holding in self._holdings.items()
            if holding.current_supply == 0
        ]
        for addr in to_remove:
            del self._holdings[addr]

    def get_holdings_to_check(self) -> Dict[str, DevHolding]:
        """Get all holdings that are active and not yet alerted."""
        return {
            addr: h for addr, h in self._holdings.items()
            if not h.has_sold and not h.is_alerted
        }

    def mark_alerted(self, token_address: str):
        """Mark a token as having triggered an alert."""
        if token_address in self._holdings:
            self._holdings[token_address].is_alerted = True


# Singleton
_dev_held_tracker: DevHeldTracker | None = None


def get_dev_held_tracker() -> DevHeldTracker:
    """Get the singleton dev held tracker."""
    global _dev_held_tracker
    if _dev_held_tracker is None:
        _dev_held_tracker = DevHeldTracker()
    return _dev_held_tracker
