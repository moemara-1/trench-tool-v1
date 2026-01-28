"""
Trench Tool V1 - DexScreener API Client
Fetches token data from DexScreener.
"""

import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TokenData:
    """Token data from DexScreener."""
    address: str
    symbol: str
    name: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    volume_24h: Optional[float]
    pair_created_at: Optional[datetime]
    dex_name: str
    pair_address: Optional[str]
    
    @property
    def age_minutes(self) -> int:
        if not self.pair_created_at:
            return 0
        delta = datetime.utcnow() - self.pair_created_at
        return int(delta.total_seconds() / 60)
    
    @property
    def age_string(self) -> str:
        """Format age as human readable string."""
        minutes = self.age_minutes
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h{mins}m" if mins else f"{hours}h"
        else:
            days = minutes // 1440
            return f"{days}d"
    
    @property
    def mc_string(self) -> str:
        """Format market cap as compact string."""
        if not self.market_cap:
            return "?"
        mc = self.market_cap
        if mc >= 1_000_000:
            return f"{mc / 1_000_000:.1f}M"
        elif mc >= 1_000:
            return f"{mc / 1_000:.1f}k"
        else:
            return f"{mc:.0f}"


class DexScreenerClient:
    """Client for DexScreener API."""
    
    BASE_URL = "https://api.dexscreener.com/latest/dex"
    
    def __init__(self):
        self._cache: dict[str, TokenData] = {}
        self._cache_ttl = 60  # seconds
        self._cache_times: dict[str, datetime] = {}
    
    async def get_token(self, token_address: str) -> Optional[TokenData]:
        """Fetch token data from DexScreener."""
        # Check cache
        if token_address in self._cache:
            cached_time = self._cache_times.get(token_address)
            if cached_time and (datetime.utcnow() - cached_time).seconds < self._cache_ttl:
                return self._cache[token_address]
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/tokens/{token_address}"
                )
                
                if response.status_code != 200:
                    logger.warning(f"DexScreener API error: {response.status_code}")
                    return None
                
                data = response.json()
                pairs = data.get("pairs", [])
                
                if not pairs:
                    return None
                
                # Use the first/best pair
                pair = pairs[0]
                base_token = pair.get("baseToken", {})
                
                # Parse creation time
                created_at = None
                if pair.get("pairCreatedAt"):
                    try:
                        created_at = datetime.fromtimestamp(pair["pairCreatedAt"] / 1000)
                    except:
                        pass
                
                token_data = TokenData(
                    address=token_address,
                    symbol=base_token.get("symbol", "???"),
                    name=base_token.get("name", "Unknown"),
                    price_usd=float(pair.get("priceUsd", 0)) if pair.get("priceUsd") else None,
                    market_cap=float(pair.get("marketCap", 0)) if pair.get("marketCap") else None,
                    liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)) if pair.get("liquidity") else None,
                    volume_24h=float(pair.get("volume", {}).get("h24", 0)) if pair.get("volume") else None,
                    pair_created_at=created_at,
                    dex_name=pair.get("dexId", "unknown"),
                    pair_address=pair.get("pairAddress"),
                )
                
                # Cache
                self._cache[token_address] = token_data
                self._cache_times[token_address] = datetime.utcnow()
                
                return token_data
                
        except Exception as e:
            logger.error(f"Error fetching token from DexScreener: {e}")
            return None
    
    def get_cached(self, token_address: str) -> Optional[TokenData]:
        """Get cached token data without making API call."""
        return self._cache.get(token_address)


# Singleton
_dex_client: DexScreenerClient | None = None


def get_dex_client() -> DexScreenerClient:
    """Get the singleton DexScreener client."""
    global _dex_client
    if _dex_client is None:
        _dex_client = DexScreenerClient()
    return _dex_client
