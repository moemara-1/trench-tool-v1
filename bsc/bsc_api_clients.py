"""
BSC API Clients
Provides token data, wallet info, and market data for BSC chain.
"""

import asyncio
import logging
import httpx
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class BSCTokenData:
    """Token data from DexScreener/BscScan."""
    address: str
    symbol: str
    name: str
    price_usd: Optional[float] = None
    market_cap: Optional[float] = None
    liquidity_usd: Optional[float] = None
    pair_address: Optional[str] = None
    dex_name: Optional[str] = None
    age_minutes: int = 0
    
    # Socials
    telegram: Optional[str] = None
    twitter: Optional[str] = None
    website: Optional[str] = None
    
    @property
    def mc_string(self) -> str:
        """Format market cap as string."""
        if self.market_cap is None:
            return "?"
        if self.market_cap >= 1_000_000_000:
            return f"{self.market_cap / 1_000_000_000:.1f}B"
        if self.market_cap >= 1_000_000:
            return f"{self.market_cap / 1_000_000:.1f}M"
        if self.market_cap >= 1_000:
            return f"{self.market_cap / 1_000:.1f}K"
        return f"{self.market_cap:.0f}"
    
    @property
    def age_string(self) -> str:
        """Format age as string."""
        if self.age_minutes < 60:
            return f"{self.age_minutes}m"
        if self.age_minutes < 1440:
            return f"{self.age_minutes // 60}h"
        return f"{self.age_minutes // 1440}d"


@dataclass
class BSCWalletInfo:
    """Wallet information from BscScan."""
    address: str
    age_days: int = 0
    tx_count: int = 0
    last_activity_days: int = 0
    funding_source: str = "Unknown"
    funding_time: Optional[datetime] = None
    
    @property
    def funding_time_ago(self) -> str:
        """Format funding time as relative string."""
        if self.funding_time is None:
            return "?"
        
        delta = datetime.utcnow() - self.funding_time
        hours = int(delta.total_seconds() / 3600)
        
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        if hours < 24:
            return f"{hours}h"
        if hours < 168:  # 7 days
            return f"{hours // 24}d"
        return f"{hours // 168}w"


# Known CEX addresses for funding source labeling
CEX_ADDRESSES = {
    "0x28C6c06298d514Db089934071355E5743bf21d60": "Binance",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": "Binance",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d": "Binance",
    "0x8894E0a0c962CB723c1976a4421c95949bE2D4E3": "Binance",
    "0xe2fc31F816A9b94326492132018C3aEcC4a93aE1": "Binance",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",
    "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE": "Binance",
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance",
    "0xA7EFAe728D2936e78BDA97dc267687568dD593f3": "OKX",
    "0x6cC5F688a315f3dC28A7781717a9A798a59fDA7b": "OKX", 
    "0x236F9F97e0E62388479bf9E5BA4889e46B0273C3": "OKX",
    "0x59fAE149A8F8ec74D5BC038F8b76D25B136b9573": "KuCoin",
    "0xf16E9B0D03470827A95CDfd0Cb8a8A3b46969B91": "KuCoin",
    "0xEB2d2F1b8c558a40207669291Fda468E50c8A0bB": "Bybit",
    "0xE3F85aAd0c8DD7337427B9dF5d0fB741d65EEEB5": "Bybit",
    "0x0D0707963952f2fBA59dD06f2b425ace40b492Fe": "Gate.io",
    "0x1C4b70a3968436B9A0a9cf5205c787eb81Bb558c": "Gate.io",
    "0x75e89d5979E4f6Fba9F97c104c2F0AFB3F1dcB88": "MEXC",
    "0x3B0C07f8fA3743E4f26f7F31b6Dbf08CEE1c3d6C": "FixedFloat",
}


class BscScanClient:
    """Client for BscScan API."""
    
    BASE_URL = "https://api.bscscan.com/api"
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._http: Optional[httpx.AsyncClient] = None
    
    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http
    
    async def get_wallet_info(self, address: str) -> BSCWalletInfo:
        """Get wallet information from BscScan."""
        try:
            http = await self._get_http()
            address_lower = address.lower()
            
            # Get transaction list to determine age and activity
            url = f"{self.BASE_URL}?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=100&sort=asc&apikey={self.api_key}"
            
            response = await http.get(url)
            data = response.json()
            
            if data.get("status") != "1" or not data.get("result"):
                return BSCWalletInfo(address=address)
            
            txs = data["result"]
            if not txs:
                return BSCWalletInfo(address=address)
            
            # First transaction (wallet creation)
            first_tx = txs[0]
            first_tx_time = datetime.fromtimestamp(int(first_tx["timeStamp"]))
            age_days = (datetime.utcnow() - first_tx_time).days
            
            # Last transaction
            last_tx = txs[-1]
            last_tx_time = datetime.fromtimestamp(int(last_tx["timeStamp"]))
            last_activity_days = (datetime.utcnow() - last_tx_time).days
            
            # Tx count
            tx_count = len(txs)
            
            # Find funding source (first incoming BNB transfer)
            funding_source = None
            funding_time = None
            
            # Check normal transactions
            for tx in txs:
                if tx["to"].lower() == address_lower and float(tx.get("value", 0)) > 0:
                    from_addr = tx["from"]
                    funding_source, funding_time = self._identify_funding_source(from_addr, tx)
                    break
            
            # If no funding found in normal txs, check internal transactions
            if funding_source is None:
                try:
                    int_url = f"{self.BASE_URL}?module=account&action=txlistinternal&address={address}&startblock=0&endblock=99999999&page=1&offset=50&sort=asc&apikey={self.api_key}"
                    int_response = await http.get(int_url)
                    int_data = int_response.json()
                    
                    if int_data.get("status") == "1" and int_data.get("result"):
                        for tx in int_data["result"]:
                            if tx.get("to", "").lower() == address_lower and float(tx.get("value", 0)) > 0:
                                from_addr = tx.get("from", "")
                                funding_source, funding_time = self._identify_funding_source(from_addr, tx)
                                break
                except Exception as e:
                    logger.debug(f"Internal tx fetch error: {e}")
            
            # Fallback to first tx sender if still no funding
            if funding_source is None:
                from_addr = txs[0].get("from", "")
                if from_addr:
                    funding_source, funding_time = self._identify_funding_source(from_addr, txs[0])
            
            return BSCWalletInfo(
                address=address,
                age_days=age_days,
                tx_count=tx_count,
                last_activity_days=last_activity_days,
                funding_source=funding_source or "Unknown",
                funding_time=funding_time,
            )
            
        except Exception as e:
            logger.error(f"BscScan error for {address[:10]}: {e}")
            return BSCWalletInfo(address=address)
    
    def _identify_funding_source(self, from_addr: str, tx: dict) -> tuple:
        """Identify funding source from address."""
        # Check if from CEX (case-insensitive)
        from_addr_lower = from_addr.lower()
        for cex_addr, cex_name in CEX_ADDRESSES.items():
            if cex_addr.lower() == from_addr_lower:
                funding_time = datetime.fromtimestamp(int(tx.get("timeStamp", 0)))
                return cex_name, funding_time
        
        # Shorten address
        funding_source = f"{from_addr[:6]}..{from_addr[-4:]}"
        funding_time = datetime.fromtimestamp(int(tx.get("timeStamp", 0)))
        return funding_source, funding_time
    
    async def close(self):
        if self._http:
            await self._http.aclose()


class BSCTokenFetcher:
    """Fetches BSC token data from DexScreener."""
    
    DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"
    
    def __init__(self):
        self._http: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple] = {}  # address -> (data, timestamp)
        self._cache_ttl = 60  # 60 second cache
    
    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http
    
    async def get_token_data(self, contract_address: str) -> Optional[BSCTokenData]:
        """Fetch token data from DexScreener."""
        try:
            # Check cache
            if contract_address in self._cache:
                data, ts = self._cache[contract_address]
                if (datetime.utcnow() - ts).total_seconds() < self._cache_ttl:
                    return data
            
            http = await self._get_http()
            url = f"{self.DEXSCREENER_URL}/{contract_address}"
            
            response = await http.get(url)
            result = response.json()
            
            pairs = result.get("pairs", [])
            if not pairs:
                return None
            
            # Find BSC pair (prioritize by liquidity)
            bsc_pairs = [p for p in pairs if p.get("chainId") == "bsc"]
            if not bsc_pairs:
                return None
            
            # Sort by liquidity
            bsc_pairs.sort(key=lambda p: p.get("liquidity", {}).get("usd", 0) or 0, reverse=True)
            pair = bsc_pairs[0]
            
            base_token = pair.get("baseToken", {})
            
            # Calculate age
            created_at = pair.get("pairCreatedAt")
            age_minutes = 0
            if created_at:
                created = datetime.fromtimestamp(created_at / 1000)
                age_minutes = int((datetime.utcnow() - created).total_seconds() / 60)
            
            # Extract socials
            info = pair.get("info", {}) or {}
            socials = info.get("socials", []) or []
            
            telegram = None
            twitter = None
            website = None
            
            for social in socials:
                s_type = social.get("type", "").lower()
                s_url = social.get("url", "")
                if "telegram" in s_type:
                    telegram = s_url
                elif "twitter" in s_type or "x.com" in s_url:
                    twitter = s_url
            
            websites = info.get("websites", []) or []
            if websites:
                website = websites[0].get("url")
            
            token_data = BSCTokenData(
                address=contract_address,
                symbol=base_token.get("symbol", "???"),
                name=base_token.get("name", "Unknown"),
                price_usd=float(pair.get("priceUsd", 0) or 0),
                market_cap=pair.get("marketCap") or pair.get("fdv"),
                liquidity_usd=pair.get("liquidity", {}).get("usd"),
                pair_address=pair.get("pairAddress"),
                dex_name=pair.get("dexId"),
                age_minutes=age_minutes,
                telegram=telegram,
                twitter=twitter,
                website=website,
            )
            
            # Cache
            self._cache[contract_address] = (token_data, datetime.utcnow())
            
            return token_data
            
        except Exception as e:
            logger.error(f"DexScreener error for {contract_address[:10]}: {e}")
            return None
    
    async def get_pair_address(self, contract_address: str) -> Optional[str]:
        """Get pair address for a token."""
        data = await self.get_token_data(contract_address)
        return data.pair_address if data else None
    
    async def close(self):
        if self._http:
            await self._http.aclose()


# Singleton instances
_bscscan_client: Optional[BscScanClient] = None
_bsc_token_fetcher: Optional[BSCTokenFetcher] = None


def get_bscscan_client() -> BscScanClient:
    """Get singleton BscScan client."""
    global _bscscan_client
    if _bscscan_client is None:
        from bsc.bsc_config import bsc_settings
        _bscscan_client = BscScanClient(api_key=bsc_settings.bscscan_api_key)
    return _bscscan_client


def get_bsc_token_fetcher() -> BSCTokenFetcher:
    """Get singleton BSC token fetcher."""
    global _bsc_token_fetcher
    if _bsc_token_fetcher is None:
        _bsc_token_fetcher = BSCTokenFetcher()
    return _bsc_token_fetcher
