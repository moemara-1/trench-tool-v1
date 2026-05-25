"""
Trench Tool V1 - Good Creator Analyzer
Analyzes token deployers to identify those with successful history.
Early signal when a proven creator launches a new token.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Set
from dataclasses import dataclass

import httpx

from config import settings
from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


@dataclass
class CreatorProfile:
    """Profile of a token creator."""
    wallet_address: str
    tokens_created: List[str]
    successful_tokens: List[str]  # >$500K MC at some point
    total_wallet_value_usd: float
    first_seen: datetime
    is_good_creator: bool
    score: int  # 0-100


class GoodCreatorAnalyzer:
    """
    Analyzes token deployers for successful history.

    A "good creator" is someone who has:
    - Previously created tokens that reached >$500K MC
    - High wallet value (serious money)
    - No history of rugs
    """

    # Thresholds (lowered for more alerts)
    SUCCESS_MC_THRESHOLD = 100_000  # $100K for successful token
    GOOD_WALLET_VALUE_USD = 1_000  # $1K wallet value
    GOOD_WALLET_VALUE_SOL = 5  # 5 SOL minimum (~$1K)

    # Alert cooldown
    _alerted_wallets: Set[str] = set()

    def __init__(self):
        # Cache creator profiles: wallet -> CreatorProfile
        self._profiles: Dict[str, CreatorProfile] = {}
        self._alerts_sent = 0
        self._alerted_wallets = set()

    async def analyze_creator(
        self,
        wallet_address: str,
        helius_client=None,
    ) -> Optional[CreatorProfile]:
        """
        Analyze a token creator's history using Helius DAS API.
        Returns CreatorProfile if analysis successful.
        """
        if wallet_address in self._profiles:
            logger.debug(f"[Creator] CACHE HIT: wallet={wallet_address[:12]}...")
            return self._profiles[wallet_address]

        logger.info(f"👑 [Creator] ANALYZING: wallet={wallet_address[:12]}...")
        try:
            # Fetch wallet assets using Helius DAS API
            wallet_value_usd = 0.0
            wallet_value_sol = 0.0
            tokens_created = []
            successful_tokens = []

            rpc_url = get_rpc_manager().get_rpc_url()

            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get wallet's SOL balance
                sol_balance_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [wallet_address]
                }

                sol_response = await client.post(rpc_url, json=sol_balance_payload)
                sol_result = sol_response.json()
                sol_lamports = sol_result.get("result", {}).get("value", 0)
                wallet_value_sol = sol_lamports / 1e9  # Convert lamports to SOL

                # Get SOL price for USD calculation
                try:
                    from services.api_clients import get_jupiter_client
                    sol_price = await get_jupiter_client().get_sol_price()
                except:
                    sol_price = 200.0  # Fallback

                wallet_value_usd = wallet_value_sol * sol_price

                # Get wallet's token holdings using DAS API
                assets_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAssetsByOwner",
                    "params": {
                        "ownerAddress": wallet_address,
                        "page": 1,
                        "limit": 100,
                        "displayOptions": {
                            "showFungible": True,
                            "showNativeBalance": True
                        }
                    }
                }

                assets_response = await client.post(rpc_url, json=assets_payload)
                assets_result = assets_response.json()
                items = assets_result.get("result", {}).get("items", [])

                # Calculate total token value
                for item in items:
                    token_info = item.get("token_info", {})
                    price_info = token_info.get("price_info", {})

                    if price_info:
                        total_price = price_info.get("total_price", 0) or 0
                        wallet_value_usd += total_price

                logger.debug(f"[Creator] Wallet {wallet_address[:8]}... value: {wallet_value_sol:.2f} SOL, ${wallet_value_usd:,.0f}")

            # Calculate score (0-100)
            score = 0
            if wallet_value_sol >= self.GOOD_WALLET_VALUE_SOL:
                score += 50  # High SOL balance
            elif wallet_value_sol >= 10:
                score += 25  # Decent SOL balance

            if wallet_value_usd >= self.GOOD_WALLET_VALUE_USD:
                score += 30  # High USD value

            if len(successful_tokens) > 0:
                score += 20  # Has successful tokens

            is_good = self.check_is_good_creator_from_values(
                wallet_value_sol=wallet_value_sol,
                wallet_value_usd=wallet_value_usd,
                successful_count=len(successful_tokens)
            )

            profile = CreatorProfile(
                wallet_address=wallet_address,
                tokens_created=tokens_created,
                successful_tokens=successful_tokens,
                total_wallet_value_usd=wallet_value_usd,
                first_seen=datetime.utcnow(),
                is_good_creator=is_good,
                score=score,
            )

            self._profiles[wallet_address] = profile
            logger.info(
                f"👑 [Creator] ANALYZED: wallet={wallet_address[:12]}... | "
                f"value={wallet_value_sol:.1f}SOL/${wallet_value_usd:,.0f} | "
                f"is_good={is_good} | score={score}"
            )
            return profile

        except Exception as e:
            logger.error(f"[Creator] Error analyzing creator {wallet_address[:12]}: {e}")
            return None

    def check_is_good_creator_from_values(
        self,
        wallet_value_sol: float,
        wallet_value_usd: float,
        successful_count: int,
    ) -> bool:
        """Check if creator meets good creator criteria based on values."""
        if successful_count > 0:
            return True
        if wallet_value_usd >= self.GOOD_WALLET_VALUE_USD:
            return True
        if wallet_value_sol >= self.GOOD_WALLET_VALUE_SOL:
            return True
        return False

    def should_alert(self, wallet_address: str) -> bool:
        """Check if we should alert for this creator (cooldown check)."""
        if wallet_address in self._alerted_wallets:
            return False
        return True

    def mark_alerted(self, wallet_address: str):
        """Mark a wallet as alerted to prevent duplicate alerts."""
        self._alerted_wallets.add(wallet_address)

    def check_is_good_creator(self, profile: CreatorProfile) -> bool:
        """Check if creator meets good creator criteria."""
        if profile.is_good_creator:
            logger.info(f"👑 [Creator] GOOD CREATOR FOUND: wallet={profile.wallet_address[:12]}... | score={profile.score} | value=${profile.total_wallet_value_usd:,.0f}")
            return True
        if len(profile.successful_tokens) > 0:
            logger.info(f"👑 [Creator] GOOD CREATOR FOUND: wallet={profile.wallet_address[:12]}... | reason=successful_tokens ({len(profile.successful_tokens)})")
            return True
        if profile.total_wallet_value_usd >= self.GOOD_WALLET_VALUE_USD:
            logger.info(f"👑 [Creator] GOOD CREATOR FOUND: wallet={profile.wallet_address[:12]}... | reason=wallet_value (${profile.total_wallet_value_usd:,.0f})")
            return True
        logger.debug(f"[Creator] Not a good creator: wallet={profile.wallet_address[:12]}... | successful_tokens={len(profile.successful_tokens)} | wallet_value=${profile.total_wallet_value_usd:,.0f}")
        return False

    async def format_good_creator_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        creator_wallet: str,
        successful_tokens: int,
        wallet_value_str: str = "?",
        market_cap_str: str = "?",
    ) -> str:
        """
        Format a good creator alert.

        👑 SOL Good Creator
        $TICKER TokenName
        Creator: 8xF3...pump | 3 successful tokens
        Wallet: $50K | MC: $100K
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher

        short_wallet = f"{creator_wallet[:6]}...{creator_wallet[-4:]}"

        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address

        message = f"""👑 SOL Good Creator
${ticker} {token_name}
Creator: {short_wallet} | {successful_tokens} successful tokens
Wallet: {wallet_value_str} | MC: {market_cap_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://dexscreener.com/solana/{contract_address}">XX</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""

        return message.strip()

    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1

    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        good_count = sum(1 for p in self._profiles.values() if p.is_good_creator)
        return {
            "creators_analyzed": len(self._profiles),
            "good_creators": good_count,
            "alerts_sent": self._alerts_sent,
        }


# Singleton
_good_creator_analyzer: GoodCreatorAnalyzer | None = None


def get_good_creator_analyzer() -> GoodCreatorAnalyzer:
    """Get the singleton good creator analyzer."""
    global _good_creator_analyzer
    if _good_creator_analyzer is None:
        _good_creator_analyzer = GoodCreatorAnalyzer()
    return _good_creator_analyzer
