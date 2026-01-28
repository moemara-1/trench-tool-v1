"""
Trench Tool V1 - Token Holder Scanner
Scans token holders to find fresh wallets.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

import httpx

from config import settings
from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


@dataclass
class FreshHolder:
    """A fresh wallet holding a token."""
    wallet_address: str
    token_balance: float
    wallet_age_hours: int
    tx_count: int
    funding_source: str
    funding_time_ago: str


class TokenHolderScanner:
    """
    Scans token holders to find fresh wallets.
    Uses Helius getTokenAccounts API.
    """
    
    def __init__(self):
        self.rpc_manager = get_rpc_manager()
        self._http_client: httpx.AsyncClient | None = None
        
        # Thresholds for fresh detection
        self.max_age_hours = 24  # Standard: 24h
        self.max_tx_count = 50   # Standard: 50
    
    async def _ensure_client(self):
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
    
    async def get_token_holders(self, token_mint: str, limit: int = 50) -> List[str]:
        """Get list of wallet addresses holding a token."""
        await self._ensure_client()
        
        try:
            # Use getTokenLargestAccounts for top holders
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [token_mint]
            }
            
            response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            
            accounts = result.get("result", {}).get("value", [])
            
            # Get owner for each token account
            holders = []
            for acc in accounts[:limit]:
                account_address = acc.get("address")
                if account_address:
                    # Get account info to find owner
                    owner = await self._get_token_account_owner(account_address)
                    if owner:
                        holders.append(owner)
            
            return holders
            
        except Exception as e:
            logger.error(f"Error getting token holders: {e}")
            return []
    
    async def _get_token_account_owner(self, token_account: str) -> Optional[str]:
        """Get the owner wallet of a token account."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    token_account,
                    {"encoding": "jsonParsed"}
                ]
            }
            
            response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            
            account_data = result.get("result", {}).get("value", {})
            if account_data:
                parsed = account_data.get("data", {}).get("parsed", {})
                info = parsed.get("info", {})
                return info.get("owner")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting token account owner: {e}")
            return None
    
    async def _get_wallet_age_and_tx_count(self, wallet_address: str) -> tuple:
        """Get wallet age in hours and transaction count."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    wallet_address,
                    {"limit": 1000}
                ]
            }
            
            response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            signatures = result.get("result", [])
            
            if not signatures:
                return 0, 0
            
            tx_count = len(signatures)
            
            oldest = signatures[-1]
            first_tx_time = datetime.fromtimestamp(oldest.get("blockTime", 0))
            age_hours = int((datetime.utcnow() - first_tx_time).total_seconds() / 3600)
            
            return age_hours, tx_count
            
        except Exception as e:
            logger.error(f"Error getting wallet age: {e}")
            return 0, 0
    
    async def scan_for_fresh_holders(self, token_mint: str, limit: int = 20) -> List[FreshHolder]:
        """
        Scan token holders and return those that are fresh wallets.
        """
        await self._ensure_client()
        
        fresh_holders = []
        
        # Get token holders
        holders = await self.get_token_holders(token_mint, limit=limit)
        
        for wallet in holders:
            # Check wallet age and tx count
            age_hours, tx_count = await self._get_wallet_age_and_tx_count(wallet)
            
            # Check if fresh
            if age_hours <= self.max_age_hours and tx_count <= self.max_tx_count:
                # Format time ago
                if age_hours < 24:
                    time_ago = f"{age_hours}h"
                else:
                    time_ago = f"{age_hours // 24}d"
                
                fresh_holders.append(FreshHolder(
                    wallet_address=wallet,
                    token_balance=0,  # Would need separate call
                    wallet_age_hours=age_hours,
                    tx_count=tx_count,
                    funding_source=f"{wallet[:4]}..{wallet[-4:]}",
                    funding_time_ago=time_ago,
                ))
        
        return fresh_holders
    
    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton
_holder_scanner: TokenHolderScanner | None = None


def get_holder_scanner() -> TokenHolderScanner:
    global _holder_scanner
    if _holder_scanner is None:
        _holder_scanner = TokenHolderScanner()
    return _holder_scanner
