"""
Trench Tool V1 - Token Transaction Tracker
Tracks all transactions for tokens to accurately count fresh/dormant buys and sells.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from collections import defaultdict

import httpx

from config import settings
from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


@dataclass
class TokenStats:
    """Statistics for a token."""
    fresh_buys: int = 0      # 👶🏻 Purchases by fresh wallets
    fresh_full_sells: int = 0    # ♦️ Full sells by fresh wallets
    fresh_partial_sells: int = 0  # 🔶 Partial sells by fresh wallets
    dormant_buys: int = 0    # ⏳ Purchases by dormant wallets
    
    # Track wallets that have bought
    fresh_holders: Dict[str, float] = field(default_factory=dict)  # wallet -> balance
    dormant_holders: Dict[str, float] = field(default_factory=dict)
    
    def record_fresh_buy(self, wallet: str, amount: float):
        """Record a fresh wallet buy."""
        self.fresh_buys += 1
        self.fresh_holders[wallet] = self.fresh_holders.get(wallet, 0) + amount
    
    def record_dormant_buy(self, wallet: str, amount: float):
        """Record a dormant wallet buy."""
        self.dormant_buys += 1
        self.dormant_holders[wallet] = self.dormant_holders.get(wallet, 0) + amount
    
    def record_fresh_sell(self, wallet: str, sold_amount: float, remaining: float):
        """Record a fresh wallet sell."""
        if wallet not in self.fresh_holders:
            return
        
        previous_balance = self.fresh_holders[wallet]
        
        if remaining <= 0 or remaining < previous_balance * 0.01:
            # Full sell (sold everything or <1% remaining)
            self.fresh_full_sells += 1
            del self.fresh_holders[wallet]
        else:
            # Partial sell
            self.fresh_partial_sells += 1
            self.fresh_holders[wallet] = remaining


class TokenTransactionTracker:
    """
    Tracks transactions for tokens to provide accurate stats.
    
    Stats tracked per token:
    - 👶🏻 fresh_buys: Purchases by fresh wallets
    - ♦️ fresh_full_sells: Full sells by fresh wallets
    - 🔶 fresh_partial_sells: Partial sells by fresh wallets
    - ⏳ dormant_buys: Purchases by dormant wallets
    """
    
    def __init__(self):
        self.rpc_manager = get_rpc_manager()
        self._http_client: httpx.AsyncClient | None = None
        
        # Stats per token
        self._token_stats: Dict[str, TokenStats] = defaultdict(TokenStats)
        
        # Wallet classification cache
        self._wallet_cache: Dict[str, dict] = {}
        self._cache_ttl = 300  # 5 minutes
        
        # Settings
        self.fresh_max_hours = 24
        self.fresh_max_tx = 50
    
    async def _ensure_client(self):
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
    
    def get_stats(self, token_address: str) -> TokenStats:
        """Get stats for a token."""
        return self._token_stats[token_address]
    
    async def classify_wallet(self, wallet_address: str) -> dict:
        """Classify a wallet as fresh, dormant, or active."""
        await self._ensure_client()
        
        # Check cache
        if wallet_address in self._wallet_cache:
            return self._wallet_cache[wallet_address]
        
        try:
            # Get wallet transactions
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [wallet_address, {"limit": 200}]
            }
            
            response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            signatures = result.get("result", [])
            
            tx_count = len(signatures)
            
            if not signatures:
                result = {
                    "is_fresh": True,
                    "is_dormant": False,
                    "age_hours": 0,
                    "tx_count": 0,
                }
            else:
                # Get age from oldest tx
                oldest = signatures[-1]
                first_tx_time = datetime.fromtimestamp(oldest.get("blockTime", 0))
                age_hours = int((datetime.utcnow() - first_tx_time).total_seconds() / 3600)
                
                # Classify
                is_fresh = age_hours <= self.fresh_max_hours and tx_count <= self.fresh_max_tx
                is_dormant = age_hours >= 720  # 30+ days inactive
                
                result = {
                    "is_fresh": is_fresh,
                    "is_dormant": is_dormant,
                    "age_hours": age_hours,
                    "tx_count": tx_count,
                }
            
            self._wallet_cache[wallet_address] = result
            return result
            
        except Exception as e:
            logger.error(f"Error classifying wallet: {e}")
            return {"is_fresh": False, "is_dormant": False, "age_hours": 0, "tx_count": 0}
    
    async def record_buy(
        self,
        token_address: str,
        wallet_address: str,
        amount_tokens: float,
        amount_sol: float,
    ) -> TokenStats:
        """Record a token purchase."""
        wallet_info = await self.classify_wallet(wallet_address)
        stats = self._token_stats[token_address]
        
        if wallet_info["is_fresh"]:
            stats.record_fresh_buy(wallet_address, amount_tokens)
        elif wallet_info["is_dormant"]:
            stats.record_dormant_buy(wallet_address, amount_tokens)
        
        return stats
    
    async def record_sell(
        self,
        token_address: str,
        wallet_address: str,
        sold_amount: float,
        remaining_balance: float,
    ) -> TokenStats:
        """Record a token sell."""
        stats = self._token_stats[token_address]
        
        # Only track fresh wallet sells
        if wallet_address in stats.fresh_holders:
            stats.record_fresh_sell(wallet_address, sold_amount, remaining_balance)
        
        return stats
    
    async def scan_token_transactions(
        self,
        token_address: str,
        limit: int = 50,
    ) -> TokenStats:
        """
        Scan recent transactions for a token and update stats.
        This provides accurate buy/sell counts.
        """
        await self._ensure_client()
        
        try:
            # Get recent signatures for the token
            # We use getSignaturesForAddress with the token mint
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [token_address, {"limit": limit}]
            }
            
            response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=payload)
            result = response.json()
            signatures = result.get("result", [])
            
            for sig_info in signatures:
                signature = sig_info.get("signature")
                
                # Get transaction
                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                }
                
                tx_response = await self._http_client.post(self.rpc_manager.get_rpc_url(), json=tx_payload)
                tx_data = tx_response.json().get("result")
                
                if tx_data:
                    await self._process_token_transaction(token_address, tx_data)
            
            return self._token_stats[token_address]
            
        except Exception as e:
            logger.error(f"Error scanning token transactions: {e}")
            return self._token_stats[token_address]
    
    async def _process_token_transaction(self, token_address: str, tx_data: dict):
        """Process a single token transaction."""
        try:
            meta = tx_data.get("meta", {})
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])
            
            # Find balance changes for this token
            for post in post_balances:
                if post.get("mint") != token_address:
                    continue
                
                owner = post.get("owner")
                post_amount = post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                
                # Find pre balance
                pre_amount = 0
                for pre in pre_balances:
                    if pre.get("mint") == token_address and pre.get("owner") == owner:
                        pre_amount = pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0
                        break
                
                if post_amount > pre_amount:
                    # Buy
                    bought = post_amount - pre_amount
                    await self.record_buy(token_address, owner, bought, 0)
                    
                elif post_amount < pre_amount:
                    # Sell
                    sold = pre_amount - post_amount
                    await self.record_sell(token_address, owner, sold, post_amount)
                    
        except Exception as e:
            logger.error(f"Error processing token transaction: {e}")
    
    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Singleton
_tx_tracker: TokenTransactionTracker | None = None


def get_tx_tracker() -> TokenTransactionTracker:
    global _tx_tracker
    if _tx_tracker is None:
        _tx_tracker = TokenTransactionTracker()
    return _tx_tracker
