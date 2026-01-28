"""
Trench Tool V1 - Wallet Classifier Service
Classifies wallets as fresh, dormant, whale, etc. based on on-chain activity.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.rpc_manager import get_rpc_manager
from models import Wallet, WalletType

logger = logging.getLogger(__name__)


class WalletClassifier:
    """Classifies wallets based on their on-chain history."""
    
    def __init__(self):
        self.rpc_manager = get_rpc_manager()
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("WalletClassifier must be used as async context manager")
        return self._client
    
    async def get_wallet_first_transaction(self, address: str) -> Optional[datetime]:
        """
        Get the timestamp of a wallet's first transaction.
        Returns None if wallet has no history.
        """
        try:
            # Get first transaction signature
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    address,
                    {"limit": 1, "before": None}
                ]
            }
            
            response = await self.client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            
            if "result" in result and result["result"]:
                # Get earliest by paginating backwards
                signatures = result["result"]
                
                # Keep paginating to find the earliest
                while True:
                    earliest_sig = signatures[-1]["signature"]
                    payload["params"][1]["before"] = earliest_sig
                    
                    response = await self.client.post(self.rpc_manager.get_rpc_url(), json=payload)
                    result = response.json()
                    
                    if not result.get("result"):
                        break
                    signatures = result["result"]
                
                # Get block time of earliest transaction
                block_time = signatures[-1].get("blockTime")
                if block_time:
                    return datetime.fromtimestamp(block_time)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting wallet first tx for {address}: {e}")
            return None
    
    async def get_wallet_last_activity(self, address: str) -> Optional[datetime]:
        """Get the timestamp of a wallet's most recent transaction."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 1}]
            }
            
            response = await self.client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            
            if "result" in result and result["result"]:
                block_time = result["result"][0].get("blockTime")
                if block_time:
                    return datetime.fromtimestamp(block_time)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting wallet last activity for {address}: {e}")
            return None
    
    async def get_wallet_transaction_count(self, address: str) -> int:
        """Get approximate transaction count for a wallet."""
        try:
            count = 0
            before = None
            
            while True:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [address, {"limit": 1000, "before": before}]
                }
                
                response = await self.client.post(self.rpc_manager.get_rpc_url(), json=payload)
                result = response.json()
                
                if "result" not in result or not result["result"]:
                    break
                
                batch_count = len(result["result"])
                count += batch_count
                
                if batch_count < 1000:
                    break
                
                before = result["result"][-1]["signature"]
                
                # Safety limit
                if count > 10000:
                    break
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting tx count for {address}: {e}")
            return 0
    
    def classify_wallet(
        self,
        first_activity: Optional[datetime],
        last_activity: Optional[datetime],
        tx_count: int = 0,
    ) -> WalletType:
        """
        Classify a wallet based on its activity patterns.
        
        Returns:
            WalletType enum value
        """
        now = datetime.utcnow()
        
        # No activity = brand new wallet
        if first_activity is None:
            return WalletType.FRESH
        
        wallet_age = now - first_activity
        
        # Fresh wallet: < 7 days old
        if wallet_age.days < settings.fresh_wallet_max_age_days:
            return WalletType.FRESH
        
        # Dormant wallet: no activity for 30+ days
        if last_activity:
            inactive_days = (now - last_activity).days
            if inactive_days >= settings.dormant_wallet_min_inactive_days:
                return WalletType.DORMANT
        
        # High transaction count could indicate bot/exchange
        if tx_count > 1000:
            return WalletType.BOT
        
        # Default to active
        return WalletType.ACTIVE
    
    async def analyze_wallet(
        self,
        address: str,
        quick_mode: bool = True
    ) -> Tuple[WalletType, dict]:
        """
        Full wallet analysis returning type and metadata.
        
        Args:
            address: Wallet address
            quick_mode: If True, only get first/last activity (faster)
        
        Returns:
            Tuple of (WalletType, metadata dict)
        """
        first_activity = await self.get_wallet_first_transaction(address)
        last_activity = await self.get_wallet_last_activity(address)
        
        tx_count = 0
        if not quick_mode:
            tx_count = await self.get_wallet_transaction_count(address)
        
        wallet_type = self.classify_wallet(first_activity, last_activity, tx_count)
        
        metadata = {
            "first_activity_at": first_activity,
            "last_activity_at": last_activity,
            "total_transactions": tx_count,
            "wallet_type": wallet_type,
            "wallet_age_days": (datetime.utcnow() - first_activity).days if first_activity else 0,
        }
        
        return wallet_type, metadata
    
    async def is_fresh_wallet(self, address: str) -> bool:
        """Quick check if wallet is fresh (< 7 days old)."""
        wallet_type, _ = await self.analyze_wallet(address, quick_mode=True)
        return wallet_type == WalletType.FRESH
    
    async def is_dormant_wallet(self, address: str) -> bool:
        """Quick check if wallet is dormant (inactive 30+ days)."""
        wallet_type, _ = await self.analyze_wallet(address, quick_mode=True)
        return wallet_type == WalletType.DORMANT


async def get_or_create_wallet(
    session: AsyncSession,
    address: str,
    classifier: WalletClassifier = None
) -> Wallet:
    """
    Get existing wallet from DB or create and classify a new one.
    """
    # Check if exists
    result = await session.execute(
        select(Wallet).where(Wallet.address == address)
    )
    wallet = result.scalar_one_or_none()
    
    if wallet:
        return wallet
    
    # Create new wallet and classify it
    wallet_type = WalletType.ACTIVE
    metadata = {}
    
    if classifier:
        wallet_type, metadata = await classifier.analyze_wallet(address, quick_mode=True)
    
    wallet = Wallet(
        address=address,
        wallet_type=wallet_type,
        first_activity_at=metadata.get("first_activity_at"),
        last_activity_at=metadata.get("last_activity_at"),
        total_transactions=metadata.get("total_transactions", 0),
    )
    
    session.add(wallet)
    return wallet
