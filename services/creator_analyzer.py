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

    # Verified creator history is required before this topic can alert.
    SUCCESS_MC_THRESHOLD = 500_000  # Pump.fun-reported historical market cap
    PUMP_FUN_CREATOR_COINS_URL = "https://frontend-api-v3.pump.fun/coins"
    PUMP_FUN_HISTORY_LIMIT = 50
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
        current_token_address: Optional[str] = None,
    ) -> Optional[CreatorProfile]:
        """Analyze a Pump.fun creator using its own launch history and wallet context."""
        if wallet_address in self._profiles:
            logger.debug(f"[Creator] CACHE HIT: wallet={wallet_address[:12]}...")
            return self._profiles[wallet_address]

        logger.info(f"[Creator] ANALYZING: wallet={wallet_address[:12]}...")
        try:
            wallet_value_sol = 0.0
            wallet_value_usd = 0.0

            async with httpx.AsyncClient(timeout=15.0) as client:
                history_items = await self._fetch_creator_history(client, wallet_address)
                if history_items is None:
                    logger.warning(
                        "[Creator] Skipping %s because Pump.fun creator history was unavailable",
                        wallet_address[:12],
                    )
                    return None

                tokens_created, successful_tokens = self._summarize_creator_history(
                    history_items,
                    wallet_address=wallet_address,
                    current_token_address=current_token_address,
                )

                if successful_tokens:
                    rpc_url = get_rpc_manager().get_rpc_url()
                    sol_balance_payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getBalance",
                        "params": [wallet_address],
                    }
                    sol_response = await client.post(rpc_url, json=sol_balance_payload)
                    sol_result = sol_response.json()
                    sol_lamports = sol_result.get("result", {}).get("value", 0)
                    wallet_value_sol = sol_lamports / 1e9

                    try:
                        from services.api_clients import get_jupiter_client

                        sol_price = await get_jupiter_client().get_sol_price()
                    except Exception:
                        sol_price = 200.0
                    wallet_value_usd = wallet_value_sol * sol_price

            score = min(80, 60 * len(successful_tokens))
            if wallet_value_sol >= self.GOOD_WALLET_VALUE_SOL:
                score += 10
            if wallet_value_usd >= self.GOOD_WALLET_VALUE_USD:
                score += 10
            score = min(100, score)

            is_good = self.check_is_good_creator_from_values(
                wallet_value_sol=wallet_value_sol,
                wallet_value_usd=wallet_value_usd,
                successful_count=len(successful_tokens),
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
                "[Creator] ANALYZED: wallet=%s... prior_tokens=%s successful=%s score=%s",
                wallet_address[:12],
                len(tokens_created),
                len(successful_tokens),
                score,
            )
            return profile
        except Exception as exc:
            logger.error(f"[Creator] Error analyzing creator {wallet_address[:12]}: {exc}")
            return None

    async def _fetch_creator_history(
        self,
        client: httpx.AsyncClient,
        wallet_address: str,
    ) -> Optional[List[dict]]:
        params = {
            "limit": self.PUMP_FUN_HISTORY_LIMIT,
            "offset": 0,
            "sort": "created_timestamp",
            "order": "DESC",
            "includeNsfw": "false",
            "creator": wallet_address,
        }
        try:
            response = await client.get(
                self.PUMP_FUN_CREATOR_COINS_URL,
                params=params,
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.warning(
                    "[Creator] Pump.fun history request failed for %s...: HTTP %s",
                    wallet_address[:12],
                    response.status_code,
                )
                return None
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning(
                "[Creator] Pump.fun history request failed for %s...: %s",
                wallet_address[:12],
                exc,
            )
            return None

        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("items"))
        if not isinstance(payload, list):
            logger.warning("[Creator] Pump.fun history returned an unexpected payload")
            return None
        return [item for item in payload if isinstance(item, dict)]

    def _summarize_creator_history(
        self,
        history_items: List[dict],
        *,
        wallet_address: str,
        current_token_address: Optional[str],
    ) -> tuple[List[str], List[str]]:
        tokens_created: List[str] = []
        successful_tokens: List[str] = []
        seen_mints: Set[str] = set()

        for item in history_items:
            mint = str(item.get("mint") or "").strip()
            creator = str(item.get("creator") or "").strip()
            if not mint or creator != wallet_address or mint == current_token_address or mint in seen_mints:
                continue
            seen_mints.add(mint)
            tokens_created.append(mint)
            ath_market_cap = self._market_cap_value(item.get("ath_market_cap"))
            current_market_cap = max(
                self._market_cap_value(item.get("usd_market_cap")),
                self._market_cap_value(item.get("market_cap_quote")),
            )
            if max(ath_market_cap, current_market_cap) >= self.SUCCESS_MC_THRESHOLD:
                successful_tokens.append(mint)

        return tokens_created, successful_tokens

    @staticmethod
    def _market_cap_value(value: object) -> float:
        if isinstance(value, bool):
            return 0.0
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
    def check_is_good_creator_from_values(
        self,
        wallet_value_sol: float,
        wallet_value_usd: float,
        successful_count: int,
    ) -> bool:
        """Require verified prior success; balance only affects ranking."""
        del wallet_value_sol, wallet_value_usd
        return successful_count > 0
    def should_alert(self, wallet_address: str) -> bool:
        """Check if we should alert for this creator (cooldown check)."""
        if wallet_address in self._alerted_wallets:
            return False
        return True

    def mark_alerted(self, wallet_address: str):
        """Mark a wallet as alerted to prevent duplicate alerts."""
        self._alerted_wallets.add(wallet_address)

    def check_is_good_creator(self, profile: CreatorProfile) -> bool:
        """Only verified successful creator history can qualify this signal."""
        is_good = profile.is_good_creator and bool(profile.successful_tokens)
        if is_good:
            logger.info(
                "[Creator] GOOD CREATOR FOUND: wallet=%s... successful_tokens=%s score=%s",
                profile.wallet_address[:12],
                len(profile.successful_tokens),
                profile.score,
            )
            return True
        logger.debug(
            "[Creator] Not a good creator: wallet=%s... successful_tokens=%s",
            profile.wallet_address[:12],
            len(profile.successful_tokens),
        )
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
Creator: {short_wallet} | {successful_tokens} verified successful launches
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
        rejected_count = len(self._profiles) - good_count
        best_score = max((profile.score for profile in self._profiles.values()), default=0)
        return {
            "creators_analyzed": len(self._profiles),
            "good_creators": good_count,
            "rejected_creators": rejected_count,
            "best_creator_score": best_score,
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
