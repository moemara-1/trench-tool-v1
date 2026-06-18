"""
Trench Tool V1 - Strongfloor Tracker
Identifies coins holding price levels and demonstrating strength over time.
Slow movers unlikely to zero suddenly - opportunities often missed until Twitter/TG mention.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class PriceLevel:
    """A tracked price level for a token."""
    price: float
    first_touched: datetime
    times_held: int


@dataclass
class StrongfloorToken:
    """A token displaying strongfloor characteristics."""
    token_address: str
    ticker: str
    token_name: str
    
    # Price tracking
    floor_price: float
    current_price: float
    time_above_floor_hours: int
    
    # Strength metrics
    bounces_from_floor: int
    floor_strength_score: int  # 0-100
    
    detected_at: datetime
    last_alert_time: Optional[datetime] = None


class StrongfloorTracker:
    """
    Tracks coins that hold price levels over time.
    """
    
    # Minimum hours holding floor to alert
    MIN_FLOOR_HOURS = 4
    # Minimum bounces to confirm floor
    MIN_BOUNCES = 2
    # Alert cooldown
    ALERT_COOLDOWN_HOURS = 24
    # State file
    STATE_FILE = "strongfloor_state.json"
    
    def __init__(self):
        # Track price history: token -> list of prices
        self._price_history: Dict[str, List[tuple]] = {}  # (price, timestamp)
        self._strongfloors: Dict[str, StrongfloorToken] = {}
        self._alerts_sent = 0
        self.load_state()
    
    def load_state(self):
        """Load alerted tokens from file."""
        import os
        import orjson
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, "rb") as f:
                    data = orjson.loads(f.read())
                    for addr, info in data.items():
                        # Reconstruct basic token info if needed, or just track alert time
                        # We primarily need the last_alert_time to prevent dupes
                        last_alert = datetime.fromisoformat(info["last_alert_time"])
                        
                        # reconstruct minimal object if not fully tracked logic (simplified)
                        # We only key off address and time for cooldown check
                        self._strongfloors[addr] = StrongfloorToken(
                            token_address=addr,
                            ticker=info.get("ticker", "?"),
                            token_name=info.get("name", "?"),
                            floor_price=0, current_price=0, time_above_floor_hours=0, bounces_from_floor=0, floor_strength_score=0, # placeholders
                            detected_at=datetime.utcnow(),
                            last_alert_time=last_alert
                        )
                logger.info(f"[Strongfloor] Loaded {len(self._strongfloors)} previous alerts from state.")
        except Exception as e:
            logger.error(f"[Strongfloor] Failed to load state: {e}")

    def save_state(self):
        """Save alerted tokens to file."""
        import orjson
        try:
            data = {}
            for addr, token in self._strongfloors.items():
                if token.last_alert_time:
                    data[addr] = {
                        "last_alert_time": token.last_alert_time.isoformat(),
                        "ticker": token.ticker,
                        "name": token.token_name
                    }
            
            with open(self.STATE_FILE, "wb") as f:
                f.write(orjson.dumps(data))
        except Exception as e:
            logger.error(f"[Strongfloor] Failed to save state: {e}")

    def record_price(self, token_address: str, price: float, ticker: str = "?", name: str = ""):
        """Record a price data point for a token."""
        is_new = token_address not in self._price_history
        if is_new:
            self._price_history[token_address] = []
        
        self._price_history[token_address].append((price, datetime.utcnow()))
        
        history_len = len(self._price_history[token_address])
        # Keep last 100 data points
        if history_len > 100:
            self._price_history[token_address] = self._price_history[token_address][-100:]
        
        if is_new:
            logger.info(f"🧱 [Strongfloor] TRACKING NEW: ${ticker} ({token_address[:12]}...) | price=${price:.8f}")
        elif history_len % 10 == 0:  # Log every 10th data point to avoid spam
            logger.debug(f"[Strongfloor] PRICE UPDATE: ${ticker} | price=${price:.8f} | history_points={history_len}")
    
    def analyze_floor(
        self,
        token_address: str,
        ticker: str,
        token_name: str,
        current_price: float,
    ) -> Optional[StrongfloorToken]:
        """
        Analyze if token has a strongfloor pattern.
        Returns StrongfloorToken if pattern detected AND not recently alerted.
        """
        if token_address not in self._price_history:
            return None
        
        # Check cooldown
        if token_address in self._strongfloors:
            existing = self._strongfloors[token_address]
            if existing.last_alert_time:
                hours_since = (datetime.utcnow() - existing.last_alert_time).total_seconds() / 3600
                if hours_since < self.ALERT_COOLDOWN_HOURS:
                    return None
        
        history = self._price_history[token_address]
        if len(history) < 10:
            return None
        
        prices = [p[0] for p in history]
        timestamps = [p[1] for p in history]
        
        # Find minimum price (potential floor)
        min_price = min(prices)
        
        # Count bounces from floor (within 5% of min)
        floor_threshold = min_price * 1.05
        bounces = 0
        was_near_floor = False
        
        for price in prices:
            if price <= floor_threshold:
                if not was_near_floor:
                    bounces += 1
                was_near_floor = True
            else:
                was_near_floor = False
        
        if bounces < self.MIN_BOUNCES:
            return None
        
        # Calculate time above floor
        first_time = timestamps[0]
        hours_tracked = (datetime.utcnow() - first_time).total_seconds() / 3600
        
        if hours_tracked < self.MIN_FLOOR_HOURS:
            return None
        
        # Calculate floor strength score
        floor_strength = min(100, bounces * 15 + int(hours_tracked * 2))
        
        strongfloor = StrongfloorToken(
            token_address=token_address,
            ticker=ticker,
            token_name=token_name,
            floor_price=min_price,
            current_price=current_price,
            time_above_floor_hours=int(hours_tracked),
            bounces_from_floor=bounces,
            floor_strength_score=floor_strength,
            detected_at=datetime.utcnow(),
            last_alert_time=None,
        )
        
        logger.info(f"🧱 [Strongfloor] FLOOR DETECTED: ${ticker} | strength={floor_strength}/100 | bounces={bounces} | hours={int(hours_tracked)}h | floor=${min_price:.8f}")
        return strongfloor
    
    async def format_strongfloor_alert(
        self,
        token: StrongfloorToken,
        market_cap_str: str = "?",
    ) -> str:
        """
        Format a strongfloor alert.
        
        🧱 SOL Strongfloor
        $TICKER TokenName | Strength: 75/100
        Floor: $0.00015 | Bounces: 4 | Time: 6h
        MC: $500K
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        floor_str = f"${token.floor_price:.6f}" if token.floor_price < 0.01 else f"${token.floor_price:.4f}"
        
        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(token.token_address)
        if not pair_address:
            pair_address = token.token_address
        
        message = f"""🧱 SOL Strongfloor
${token.ticker} {token.token_name} | Strength: {token.floor_strength_score}/100
Floor: {floor_str} | Bounces: {token.bounces_from_floor} | Time: {token.time_above_floor_hours}h
MC: {market_cap_str}
<code>{token.token_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{token.token_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={token.token_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={token.token_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{token.token_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={token.token_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={token.token_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={token.token_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={token.token_address}">NE</a> | <a href="https://dexscreener.com/solana/{token.token_address}">XX</a> | <a href="https://pump.fun/{token.token_address}">PF</a>"""
        
        return message.strip()
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1

    def mark_alerted(self, token: StrongfloorToken):
        """Persist alert cooldown after Telegram delivery succeeds."""
        alerted = StrongfloorToken(
            token_address=token.token_address,
            ticker=token.ticker,
            token_name=token.token_name,
            floor_price=token.floor_price,
            current_price=token.current_price,
            time_above_floor_hours=token.time_above_floor_hours,
            bounces_from_floor=token.bounces_from_floor,
            floor_strength_score=token.floor_strength_score,
            detected_at=token.detected_at,
            last_alert_time=datetime.utcnow(),
        )
        self._strongfloors[token.token_address] = alerted
        self.save_state()
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "tokens_tracked": len(self._price_history),
            "strongfloors_detected": len(self._strongfloors),
            "alerts_sent": self._alerts_sent,
        }


# Singleton
_strongfloor_tracker: StrongfloorTracker | None = None


def get_strongfloor_tracker() -> StrongfloorTracker:
    """Get the singleton strongfloor tracker."""
    global _strongfloor_tracker
    if _strongfloor_tracker is None:
        _strongfloor_tracker = StrongfloorTracker()
    return _strongfloor_tracker
