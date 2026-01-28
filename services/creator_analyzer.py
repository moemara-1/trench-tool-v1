"""
Trench Tool V1 - Good Creator Analyzer
Analyzes token deployers to identify those with successful history.
Early signal when a proven creator launches a new token.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

from config import settings

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

    # Thresholds
    SUCCESS_MC_THRESHOLD = 500_000  # $500K
    GOOD_WALLET_VALUE_USD = 10_000  # $10K wallet value

    def __init__(self):
        # Cache creator profiles: wallet -> CreatorProfile
        self._profiles: Dict[str, CreatorProfile] = {}
        self._alerts_sent = 0

    async def analyze_creator(
        self,
        wallet_address: str,
        helius_client=None,
    ) -> Optional[CreatorProfile]:
        """
        Analyze a token creator's history.
        Returns CreatorProfile if analysis successful.
        """
        if wallet_address in self._profiles:
            logger.debug(f"[Creator] CACHE HIT: wallet={wallet_address[:12]}...")
            return self._profiles[wallet_address]

        logger.info(f"👑 [Creator] ANALYZING: wallet={wallet_address[:12]}...")
        try:
            # Would need to fetch wallet's token creation history
            # For now, create a placeholder profile
            profile = CreatorProfile(
                wallet_address=wallet_address,
                tokens_created=[],
                successful_tokens=[],
                total_wallet_value_usd=0,
                first_seen=datetime.utcnow(),
                is_good_creator=False,
                score=0,
            )

            # Check wallet value if helius client available
            if helius_client:
                # Fetch wallet assets and calculate value
                # This would be implemented with Helius DAS API
                logger.debug(f"[Creator] Helius client available, would fetch wallet assets")
            else:
                logger.debug(f"[Creator] No Helius client, using placeholder profile")

            self._profiles[wallet_address] = profile
            logger.info(f"👑 [Creator] ANALYZED: wallet={wallet_address[:12]}... | is_good={profile.is_good_creator} | score={profile.score} | total_profiles={len(self._profiles)}")
            return profile

        except Exception as e:
            logger.error(f"[Creator] Error analyzing creator {wallet_address[:12]}: {e}")
            return None

    def check_is_good_creator(self, profile: CreatorProfile) -> bool:
        """Check if creator meets good creator criteria."""
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
