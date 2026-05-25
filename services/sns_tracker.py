"""
Trench Tool V1 - SNS Tracker
Monitors purchases made by wallets with Solana Name Service (SNS) domains.
SNS domains indicate serious/established wallet owners.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

import httpx

from config import settings
from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


@dataclass
class SNSWalletInfo:
    """Info about a wallet with SNS domain."""
    wallet_address: str
    domain_name: str  # e.g., "ilikesex.sol"
    last_tx_time: Optional[datetime] = None
    last_tx_hours_ago: int = 0


class SNSTracker:
    """
    Tracks purchases by wallets with SNS (.sol) domains.
    
    Uses Helius API to look up SNS domains for wallets.
    """
    
    def __init__(self):
        self._domain_cache: Dict[str, Optional[str]] = {}  # wallet -> domain
        self._sns_buys: Dict[str, int] = {}  # token -> count
        self._alerts_sent = 0
    
    async def get_wallet_domain(self, wallet_address: str) -> Optional[str]:
        """Look up SNS domain for a wallet using Helius API."""
        
        # Check cache first
        if wallet_address in self._domain_cache:
            cached = self._domain_cache[wallet_address]
            if cached:
                logger.info(f"🏷️ SNS cache hit: {cached} for {wallet_address[:8]}...")
            return cached
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Helius DAS API for domain lookup (requires Helius endpoint)
                rpc_url = get_rpc_manager().get_rpc_url()
                response = await client.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getAssetsByOwner",
                        "params": {
                            "ownerAddress": wallet_address,
                            "page": 1,
                            "limit": 100,
                            "displayOptions": {"showUnverifiedCollections": True}
                        }
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("result", {}).get("items", [])
                    
                    # Log asset count for debugging
                    logger.info(f"🏷️ SNS lookup: {len(items)} assets for {wallet_address[:8]}...")
                    
                    for item in items:
                        # Look for SNS domain NFTs
                        content = item.get("content", {})
                        metadata = content.get("metadata", {})
                        name = metadata.get("name", "")
                        
                        if name.endswith(".sol"):
                            self._domain_cache[wallet_address] = name
                            logger.info(f"🏷️ Found SNS domain: {name} for wallet {wallet_address[:8]}...")
                            return name
                else:
                    logger.info(f"SNS lookup failed: HTTP {response.status_code} for {wallet_address[:8]}")
            
            # No domain found, cache negative result
            self._domain_cache[wallet_address] = None
            return None
            
        except Exception as e:
            logger.info(f"SNS lookup error for {wallet_address[:8]}: {e}")
            return None
    
    async def format_sns_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        domain_name: str,
        amount_sol: float,
        market_cap_str: str,
        coin_age_str: str,
        last_tx_hours_ago: int = 0,
        is_first_mention: bool = False,
        is_whale: bool = False,
        is_dolphin: bool = False,
    ) -> str:
        """
        Format an SNS Buys alert in BBB style:
        
        🏷️ SNS Buys [BBB]
        🐳 $TICKER name domain.sol AMOUNT TIME
        MC: X | CA: X
        CONTRACT
        Twitter
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        # Build emoji indicators
        emojis = []
        if is_first_mention:
            emojis.append("⭐️")
        if is_whale:
            emojis.append("🐳")
        elif is_dolphin:
            emojis.append("🐬")
        
        emoji_str = " ".join(emojis) + (" " if emojis else "")
        
        # Time format
        time_str = f"{last_tx_hours_ago}h" if last_tx_hours_ago < 48 else f"{last_tx_hours_ago // 24}d"
        
        # Get pair address for Axiom link
        from services.api_clients import get_token_fetcher
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address
        
        message = f"""🏷️ SNS Buys
{emoji_str}${ticker} {token_name} {domain_name} {amount_sol:.2f} {time_str}
MC: {market_cap_str} | CA: {coin_age_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    def track_sns_buy(self, token_address: str) -> int:
        """Track an SNS buy and return the count."""
        if token_address not in self._sns_buys:
            self._sns_buys[token_address] = 0
        self._sns_buys[token_address] += 1
        return self._sns_buys[token_address]
    
    def increment_alerts_sent(self):
        """Increment alerts sent counter."""
        self._alerts_sent += 1
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "domains_cached": len(self._domain_cache),
            "domains_found": sum(1 for d in self._domain_cache.values() if d),
            "sns_buys_tracked": sum(self._sns_buys.values()),
            "alerts_sent": self._alerts_sent,
        }


# Singleton
_sns_tracker: SNSTracker | None = None


def get_sns_tracker() -> SNSTracker:
    """Get the singleton SNS tracker."""
    global _sns_tracker
    if _sns_tracker is None:
        _sns_tracker = SNSTracker()
    return _sns_tracker

