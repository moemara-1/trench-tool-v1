"""
Trench Tool V1 - Late Migration Tracker
Detects pump.fun tokens that bond late (1+ days after launch).
Late bondings can indicate OG meme revivals or strategic timing.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

import httpx

from config import settings

logger = logging.getLogger(__name__)

# pump.fun program ID
PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Raydium AMM program (migration target after bonding)
RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"


@dataclass
class LateBonding:
    """A detected late bonding event."""
    token_address: str
    launch_time: datetime
    bonding_time: datetime
    delay_hours: int
    delay_days: float
    is_late: bool  # True if >= 24 hours (1 day) delay


class LateMigrationTracker:
    """
    Tracks pump.fun tokens for late bondings.
    
    A "late migration/bonding" occurs when a token bonds (completes 
    its bonding curve) a day or more AFTER it was originally launched.
    
    This pattern can indicate:
    - OG meme revivals (old coins getting new attention)
    - Insider accumulation before completion
    - Strategic timing for maximum impact
    """
    
    # Threshold for "late" bonding (hours) - 24 hours = 1 day
    LATE_THRESHOLD_HOURS = 24
    
    def __init__(self):
        # Track late bondings: token -> LateBonding
        self._late_bondings: Dict[str, LateBonding] = {}
        self._alerts_sent = 0
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client
    
    async def get_token_launch_time(self, token_address: str) -> Optional[datetime]:
        """
        Fetch when a token was first created/launched on pump.fun.
        Uses DexScreener API to get pair creation time.
        """
        try:
            client = await self.get_client()
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = await client.get(url)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                return None
            
            # Find the earliest pair creation time (token launch)
            earliest_time = None
            for pair in pairs:
                created_at = pair.get("pairCreatedAt")
                if created_at:
                    # pairCreatedAt is in milliseconds
                    pair_time = datetime.utcfromtimestamp(created_at / 1000)
                    if earliest_time is None or pair_time < earliest_time:
                        earliest_time = pair_time
            
            return earliest_time
            
        except Exception as e:
            logger.debug(f"[LateMigration] Error fetching launch time for {token_address[:12]}: {e}")
            return None
    
    async def check_late_bonding(
        self,
        token_address: str,
        program_ids: list,
    ) -> Optional[LateBonding]:
        """
        Check if a bonding curve completion happened late (1+ day after launch).
        
        Args:
            token_address: The token mint address
            program_ids: Program IDs from the transaction
            
        Returns:
            LateBonding if this is a late bonding event, None otherwise
        """
        # Only check pump.fun + Raydium migrations (bonding curve completions)
        if PUMPFUN_PROGRAM not in program_ids:
            return None
        
        # Raydium AMM indicates the bonding curve completed and migrated
        if RAYDIUM_AMM not in program_ids:
            return None
        
        # Already tracked this token
        if token_address in self._late_bondings:
            return None
        
        logger.debug(f"[LateMigration] Checking bonding for {token_address[:12]}...")
        
        # Get when this token was originally launched
        launch_time = await self.get_token_launch_time(token_address)
        
        if not launch_time:
            logger.debug(f"[LateMigration] Could not fetch launch time for {token_address[:12]}")
            return None
        
        bonding_time = datetime.utcnow()
        delay = bonding_time - launch_time
        delay_hours = int(delay.total_seconds() / 3600)
        delay_days = delay.total_seconds() / 86400  # 86400 seconds in a day
        
        is_late = delay_hours >= self.LATE_THRESHOLD_HOURS
        
        if is_late:
            late_bonding = LateBonding(
                token_address=token_address,
                launch_time=launch_time,
                bonding_time=bonding_time,
                delay_hours=delay_hours,
                delay_days=delay_days,
                is_late=True,
            )
            
            self._late_bondings[token_address] = late_bonding
            
            logger.info(
                f"🕐 [LateMigration] LATE BONDING DETECTED: "
                f"token={token_address[:12]}... | "
                f"launched={delay_days:.1f}d ago | "
                f"threshold={self.LATE_THRESHOLD_HOURS}h"
            )
            
            return late_bonding
        else:
            logger.debug(
                f"[LateMigration] Normal bonding: {token_address[:12]}... | "
                f"launched={delay_hours}h ago (threshold={self.LATE_THRESHOLD_HOURS}h)"
            )
            return None
    
    async def format_late_migration_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        delay_hours: int,
        market_cap_str: str = "?",
    ) -> str:
        """
        Format a late bonding alert.
        
        🕐 SOL Late Bonding
        $TICKER TokenName | Bonded 2d after launch
        MC: $500K
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        # Format delay nicely
        if delay_hours >= 24:
            days = delay_hours / 24
            delay_str = f"{days:.1f}d after launch"
        else:
            delay_str = f"{delay_hours}h after launch"
        
        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address
        
        message = f"""🕐 SOL Late Bonding
${ticker} {token_name} | Bonded {delay_str}
MC: {market_cap_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://dexscreener.com/solana/{contract_address}">XX</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    def cleanup_old_bondings(self, max_age_hours: int = 24):
        """Remove old bonding records to prevent memory buildup."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        old_tokens = [
            token for token, bonding in self._late_bondings.items()
            if bonding.bonding_time < cutoff
        ]
        for token in old_tokens:
            del self._late_bondings[token]
        if old_tokens:
            logger.debug(f"[LateMigration] Cleaned up {len(old_tokens)} old bonding records")
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "pending_bondings": 0,  # Not used anymore
            "migrations_detected": len(self._late_bondings),
            "alerts_sent": self._alerts_sent,
        }


# Singleton
_late_migration_tracker: LateMigrationTracker | None = None


def get_late_migration_tracker() -> LateMigrationTracker:
    """Get the singleton late migration tracker."""
    global _late_migration_tracker
    if _late_migration_tracker is None:
        _late_migration_tracker = LateMigrationTracker()
    return _late_migration_tracker
