"""
Trench Tool V1 - SNS Tracker
Monitors purchases made by wallets with Solana Name Service (SNS) domains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import httpx

from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


@dataclass
class SNSWalletInfo:
    """Info about a wallet with an SNS domain."""

    wallet_address: str
    domain_name: str
    last_tx_time: Optional[datetime] = None
    last_tx_hours_ago: int = 0


class SNSTracker:
    """Tracks purchases by wallets with SNS (.sol) domains."""

    def __init__(self):
        self._domain_cache: Dict[str, Optional[str]] = {}
        self._sns_buys: Dict[str, int] = {}
        self._alerts_sent = 0

    async def get_wallet_domain(self, wallet_address: str) -> Optional[str]:
        """Look up SNS domain for a wallet using a DAS-capable Solana RPC."""
        if wallet_address in self._domain_cache:
            cached = self._domain_cache[wallet_address]
            if cached:
                logger.info("SNS cache hit: %s for %s...", cached, wallet_address[:8])
            return cached

        try:
            rpc_manager = get_rpc_manager()
            max_attempts = max(1, rpc_manager.endpoint_count)
            async with httpx.AsyncClient(timeout=10.0) as client:
                for _ in range(max_attempts):
                    rpc_url = rpc_manager.get_rpc_url()
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
                                "displayOptions": {"showUnverifiedCollections": True},
                            },
                        },
                    )

                    if response.status_code in {429, 500, 502, 503, 504}:
                        rpc_manager.report_error(rpc_url, is_rate_limit=response.status_code == 429)
                        logger.info(
                            "SNS lookup transient HTTP %s for %s, retrying",
                            response.status_code,
                            wallet_address[:8],
                        )
                        continue

                    if response.status_code != 200:
                        logger.info("SNS lookup failed: HTTP %s for %s", response.status_code, wallet_address[:8])
                        continue

                    data = response.json()
                    if data.get("error"):
                        logger.info("SNS lookup RPC error for %s: %s", wallet_address[:8], data.get("error"))
                        continue

                    items = data.get("result", {}).get("items", [])
                    logger.info("SNS lookup: %s assets for %s...", len(items), wallet_address[:8])

                    for item in items:
                        content = item.get("content", {})
                        metadata = content.get("metadata", {})
                        name = metadata.get("name", "")
                        if name.endswith(".sol"):
                            self._domain_cache[wallet_address] = name
                            logger.info("Found SNS domain: %s for wallet %s...", name, wallet_address[:8])
                            return name

                    # A successful DAS response with no SNS domain is a reliable negative.
                    break

            self._domain_cache[wallet_address] = None
            return None

        except Exception as exc:
            logger.info("SNS lookup error for %s: %s", wallet_address[:8], exc)
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
        """Format an SNS Buys alert in BBB style."""
        emojis = []
        if is_first_mention:
            emojis.append("STAR")
        if is_whale:
            emojis.append("WHALE")
        elif is_dolphin:
            emojis.append("DOLPHIN")

        emoji_str = " ".join(emojis) + (" " if emojis else "")
        time_str = f"{last_tx_hours_ago}h" if last_tx_hours_ago < 48 else f"{last_tx_hours_ago // 24}d"

        from services.api_clients import get_token_fetcher

        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address

        message = f"""SNS Buys
{emoji_str}${ticker} {token_name} {domain_name} {amount_sol:.2f} {time_str}
MC: {market_cap_str} | CA: {coin_age_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""

        return message.strip()

    def track_sns_buy(self, token_address: str) -> int:
        """Track an SNS buy and return the count."""
        self._sns_buys[token_address] = self._sns_buys.get(token_address, 0) + 1
        return self._sns_buys[token_address]

    def increment_alerts_sent(self):
        """Increment alerts sent counter."""
        self._alerts_sent += 1

    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "domains_cached": len(self._domain_cache),
            "domains_found": sum(1 for domain in self._domain_cache.values() if domain),
            "sns_buys_tracked": sum(self._sns_buys.values()),
            "alerts_sent": self._alerts_sent,
        }


_sns_tracker: SNSTracker | None = None


def get_sns_tracker() -> SNSTracker:
    """Get the singleton SNS tracker."""
    global _sns_tracker
    if _sns_tracker is None:
        _sns_tracker = SNSTracker()
    return _sns_tracker
