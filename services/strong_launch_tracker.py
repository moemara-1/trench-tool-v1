"""
Trench Tool V1 - Strong Launch Tracker
Curated channel for potential runners with filtered rugs.
Aggregates multiple signals to identify high-upside plays.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class StrongLaunch:
    """A detected strong launch candidate."""
    token_address: str
    ticker: str
    token_name: str
    
    # Criteria scores
    creator_score: int  # 0-100
    social_score: int  # 0-100
    tokenomics_score: int  # 0-100
    buy_pressure_score: int  # 0-100
    
    # Aggregated
    total_score: int
    is_strong: bool
    
    # Metadata
    market_cap: float
    detected_at: datetime


class StrongLaunchTracker:
    """
    Identifies potential runners through curated signals.
    
    Strong launches have:
    - Good creator (not linked to rugs)
    - Clean tokenomics (low bundle, no insider supply)
    - Organic buy pressure
    - Social presence
    
    This channel is noisier (5-10 alerts/day) but curated
    to remove obvious rugs.
    """
    
    # Minimum total score to alert
    MIN_SCORE_THRESHOLD = 55
    
    def __init__(self):
        self._launches: Dict[str, StrongLaunch] = {}
        self._alerts_sent = 0
        self._candidates_evaluated = 0
        self._rejected_by_reason: Dict[str, int] = defaultdict(int)    
    def evaluate_launch(
        self,
        token_address: str,
        ticker: str,
        token_name: str,
        market_cap: float,
        creator_score: int = 50,
        social_score: int = 0,
        tokenomics_score: int = 50,
        buy_pressure_score: int = 50,
        age_minutes: int = 0,
    ) -> Optional[StrongLaunch]:
        """
        Evaluate if a token is a strong launch candidate.
        Returns StrongLaunch if it meets criteria.
        """
        logger.debug(f"[StrongLaunch] EVALUATING: ${ticker} ({token_address[:12]}...) | creator={creator_score} | social={social_score} | tokenomics={tokenomics_score} | pressure={buy_pressure_score} | age={age_minutes}m")
        self._candidates_evaluated += 1
        
        # Filter out old launches (must be < 1 hour old)
        if age_minutes > 60:
             logger.debug(f"[StrongLaunch] REJECTED: ${ticker} too old ({age_minutes}m > 60m)")
             self._record_rejection("too_old")
             return None

        # Calculate total score (weighted average)
        total_score = (
            creator_score * 0.25 +
            social_score * 0.20 +
            tokenomics_score * 0.30 +
            buy_pressure_score * 0.25
        )
        
        is_strong = total_score >= self.MIN_SCORE_THRESHOLD
        
        launch = StrongLaunch(
            token_address=token_address,
            ticker=ticker,
            token_name=token_name,
            creator_score=creator_score,
            social_score=social_score,
            tokenomics_score=tokenomics_score,
            buy_pressure_score=buy_pressure_score,
            total_score=int(total_score),
            is_strong=is_strong,
            market_cap=market_cap,
            detected_at=datetime.utcnow(),
        )
        
        if is_strong:
            self._launches[token_address] = launch
            logger.info(f"🚀 [StrongLaunch] STRONG LAUNCH DETECTED: ${ticker} | score={int(total_score)}/100 | threshold={self.MIN_SCORE_THRESHOLD} | total_launches={len(self._launches)}")
        else:
            logger.debug(f"[StrongLaunch] NOT STRONG: ${ticker} | score={int(total_score)}/100 | threshold={self.MIN_SCORE_THRESHOLD}")
            self._record_rejection("score_below_threshold")
        
        return launch if is_strong else None
    
    async def format_strong_launch_alert(
        self,
        launch: StrongLaunch,
        market_cap_str: str = "?",
        coin_age_str: str = "?",
    ) -> str:
        """
        Format a strong launch alert.
        
        🚀 SOL Strong Launch
        $TICKER TokenName | Score: 75/100
        Creator: 80 | Social: 60 | Tokenomics: 85 | Pressure: 75
        MC: $100K | CA: 5m
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        scores = f"Creator: {launch.creator_score} | Social: {launch.social_score} | Tokenomics: {launch.tokenomics_score} | Pressure: {launch.buy_pressure_score}"
        
        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(launch.token_address)
        if not pair_address:
            pair_address = launch.token_address
        
        message = f"""🚀 SOL Strong Launch
${launch.ticker} {launch.token_name} | Score: {launch.total_score}/100
{scores}
MC: {market_cap_str} | CA: {coin_age_str}
<code>{launch.token_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{launch.token_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={launch.token_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={launch.token_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{launch.token_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={launch.token_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={launch.token_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={launch.token_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={launch.token_address}">NE</a> | <a href="https://dexscreener.com/solana/{launch.token_address}">XX</a> | <a href="https://pump.fun/{launch.token_address}">PF</a>"""
        
        return message.strip()
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1

    def _record_rejection(self, reason: str):
        self._rejected_by_reason[reason] += 1
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "strong_launches": len(self._launches),
            "alerts_sent": self._alerts_sent,
            "candidates_evaluated": self._candidates_evaluated,
            "rejected_by_reason": dict(sorted(self._rejected_by_reason.items())),
        }


# Singleton
_strong_launch_tracker: StrongLaunchTracker | None = None


def get_strong_launch_tracker() -> StrongLaunchTracker:
    """Get the singleton strong launch tracker."""
    global _strong_launch_tracker
    if _strong_launch_tracker is None:
        _strong_launch_tracker = StrongLaunchTracker()
    return _strong_launch_tracker
