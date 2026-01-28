"""
Trench Tool V1 - Bundle Detector
Detects coordinated trading patterns and potential rug pulls.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Wallet, Token, Freshie, Alert, AlertPriority, TradeAction

logger = logging.getLogger(__name__)


@dataclass
class BundleInfo:
    """Information about a detected bundle (coordinated activity)."""
    bundle_id: str
    token_address: str
    wallets: List[str]
    wallet_count: int
    total_volume_sol: float
    total_token_amount: float
    action: str  # "buy" or "sell"
    coordination_score: float  # 0-100
    time_window_seconds: int
    first_tx_time: datetime
    last_tx_time: datetime
    is_potential_rug: bool
    
    # BBB fields
    supply_percent: float = 0.0  # % of total supply acquired
    wallet_breakdown: List[dict] = field(default_factory=list)  # [{wallet, sol, time}]
    block_number: int = 0
    is_opening_bundle: bool = False
    
    # For Bundle Sales
    total_exits: int = 0
    partial_exits: int = 0
    full_exits: int = 0
    supply_remaining: float = 0.0


@dataclass
class WalletCluster:
    """A cluster of related wallets."""
    wallets: Set[str] = field(default_factory=set)
    funding_sources: Set[str] = field(default_factory=set)
    common_tokens: Set[str] = field(default_factory=set)


class BundleDetector:
    """
    Detects coordinated trading patterns including:
    - Bundle buys: Multiple wallets buying same token in short timeframe
    - Bundle sells: Coordinated selling (potential rug pull)
    - Wallet clusters: Wallets funded from same source
    """
    
    def __init__(self):
        # Detection thresholds - Balanced for detecting real bundles
        self.min_wallets_for_bundle = 3  # Need 3+ wallets buying same block
        self.min_wallet_amount_sol = 0.3 # User request: 0.3 SOL not dust
        self.time_window_seconds = 60    # Reduced for same-block focus
        self.coordination_threshold = 50  # Lowered to catch more bundles
        
        # Track recent transactions by token
        self._recent_txs: Dict[str, List[dict]] = defaultdict(list)
        self._detected_bundles: Dict[str, BundleInfo] = {}
        
        # Wallet clustering
        self._funding_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Opening block tracking
        self._first_block_seen: Dict[str, int] = {}
        self.min_supply_pct_for_opening = 0.5  # Adjust as needed
    
    def add_transaction(
        self,
        token_address: str,
        wallet_address: str,
        amount_sol: float,
        token_amount: float = 0.0,
        action: TradeAction = TradeAction.BUY,
        timestamp: datetime = None,
        block_number: int = 0,
        funding_source: str = None,
    ) -> Optional[BundleInfo]:
        """
        Add a transaction and check if it forms a bundle.
        
        Returns BundleInfo if a bundle is detected.
        """
        timestamp = timestamp or datetime.utcnow()
        
        # Track opening block
        if block_number > 0 and token_address not in self._first_block_seen:
            self._first_block_seen[token_address] = block_number
            logger.info(f"🆕 First block seen for {token_address[:8]}: {block_number}")
        
        # Track funding relationships
        if funding_source:
            self._funding_graph[funding_source].add(wallet_address)
        
        # Add to recent transactions
        tx_data = {
            "wallet": wallet_address,
            "amount_sol": amount_sol,
            "token_amount": token_amount,
            "action": action.value if isinstance(action, TradeAction) else action,
            "timestamp": timestamp,
            "block_number": block_number,
            "funding_source": funding_source,
        }
        
        self._recent_txs[token_address].append(tx_data)
        
        # Clean old transactions
        self._clean_old_transactions(token_address)
        
        # Check for bundle
        return self._detect_bundle(token_address)
    
    def _clean_old_transactions(self, token_address: str):
        """Remove transactions older than the time window."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.time_window_seconds * 2)
        self._recent_txs[token_address] = [
            tx for tx in self._recent_txs[token_address]
            if tx["timestamp"] > cutoff
        ]
    
    def _detect_bundle(self, token_address: str) -> Optional[BundleInfo]:
        """Check if recent transactions form a bundle."""
        recent = self._recent_txs[token_address]
        
        if len(recent) < self.min_wallets_for_bundle:
            return None
        
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.time_window_seconds)
        
        # Filter to time window
        window_txs = [tx for tx in recent if tx["timestamp"] > window_start]
        
        # Log for debugging
        unique_wallets = len(set(tx["wallet"] for tx in window_txs))
        logger.info(f"📦 Bundle check: {len(window_txs)} txs, {unique_wallets} unique wallets in {self.time_window_seconds}s for {token_address[:8]}...")
        
        if len(window_txs) < self.min_wallets_for_bundle:
            return None
        
        # Group by action (buy vs sell)
        buys = [tx for tx in window_txs if tx["action"] == "buy" and tx["amount_sol"] >= self.min_wallet_amount_sol]
        sells = [tx for tx in window_txs if tx["action"] in ("full_sell", "partial_sell")]
        
        # Check for bundle buys (Grouped by block)
        if buys:
            # Group by block number
            blocks = defaultdict(list)
            for b in buys:
                blocks[b["block_number"]].append(b)
            
            for block_num, block_txs in blocks.items():
                unique_block_wallets = len(set(tx["wallet"] for tx in block_txs))
                if unique_block_wallets >= self.min_wallets_for_bundle:
                    logger.info(f"📦 SAME-BLOCK Bundle BUY detected in block {block_num}: {unique_block_wallets} wallets for {token_address[:8]}...")
                    # Is this an opening bundle? (Simplified: if block_num is small or first seen)
                    # More accurately, we can check token age via fetcher later
                    return self._create_bundle_info(token_address, block_txs, "buy", block_num)
        
        # Check for bundle sells (potential rug)
        unique_sell_wallets = len(set(tx["wallet"] for tx in sells))
        if unique_sell_wallets >= self.min_wallets_for_bundle:
            logger.info(f"📦 Bundle SELL detected: {unique_sell_wallets} wallets for {token_address[:8]}...")
            return self._create_bundle_info(token_address, sells, "sell")
        
        return None
    
    def _create_bundle_info(
        self,
        token_address: str,
        transactions: List[dict],
        action: str,
        block_number: int = 0,
    ) -> BundleInfo:
        """Create a BundleInfo from detected transactions."""
        wallets = list(set(tx["wallet"] for tx in transactions))
        total_volume_sol = sum(tx["amount_sol"] for tx in transactions)
        total_token_amount = sum(tx.get("token_amount", 0) for tx in transactions)
        
        # Calculate coordination score
        coordination_score = self._calculate_coordination_score(transactions)
        
        # Determine if potential rug
        is_potential_rug = (
            action == "sell" and 
            coordination_score >= 80 and 
            total_volume_sol >= 10
        )
        
        timestamps = [tx["timestamp"] for tx in transactions]
        
        bundle_id = f"{token_address[:8]}_{action}_{len(wallets)}_{int(datetime.utcnow().timestamp())}"
        
        # Determine if opening bundle: specifically the first block containing buys we've seen
        first_block = self._first_block_seen.get(token_address, 0)
        is_opening = (
            action == "buy" and 
            block_number > 0 and 
            block_number == first_block
        )
        
        info = BundleInfo(
            bundle_id=bundle_id,
            token_address=token_address,
            wallets=wallets,
            wallet_count=len(wallets),
            total_volume_sol=total_volume_sol,
            total_token_amount=total_token_amount,
            action=action,
            coordination_score=coordination_score,
            time_window_seconds=int((max(timestamps) - min(timestamps)).total_seconds()),
            first_tx_time=min(timestamps),
            last_tx_time=max(timestamps),
            is_potential_rug=is_potential_rug,
            block_number=block_number,
            is_opening_bundle=is_opening,
            # Populate wallet breakdown with each wallet's SOL amount
            wallet_breakdown=[
                {"wallet": tx["wallet"], "sol": tx["amount_sol"]}
                for tx in transactions
            ],
        )
        
        self._detected_bundles[bundle_id] = info
        return info
    
    def _calculate_coordination_score(self, transactions: List[dict]) -> float:
        """
        Calculate a coordination score (0-100) based on:
        - Time clustering: How close together are the transactions
        - Funding source: Same funding source = higher score
        - Amount similarity: Similar amounts = higher score
        """
        if len(transactions) < 2:
            return 0.0
        
        # Time clustering (0-40 points)
        timestamps = [tx["timestamp"] for tx in transactions]
        time_span = (max(timestamps) - min(timestamps)).total_seconds()
        time_score = max(0, 40 - (time_span / self.time_window_seconds) * 40)
        
        # Funding source (0-30 points)
        funding_sources = [tx.get("funding_source") for tx in transactions if tx.get("funding_source")]
        if funding_sources:
            unique_sources = len(set(funding_sources))
            funding_score = 30 * (1 - (unique_sources - 1) / len(funding_sources))
        else:
            funding_score = 0
        
        # Amount similarity (0-30 points)
        amounts = [tx["amount_sol"] for tx in transactions]
        avg_amount = sum(amounts) / len(amounts)
        variance = sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)
        # Lower variance = higher score
        amount_score = max(0, 30 - (variance / avg_amount) * 10) if avg_amount > 0 else 0
        
        return min(100, time_score + funding_score + amount_score)
    
    def get_wallet_cluster(self, wallet_address: str) -> WalletCluster:
        """Get the cluster of wallets related to this wallet."""
        cluster = WalletCluster()
        cluster.wallets.add(wallet_address)
        
        # Find wallets with same funding source
        for source, funded_wallets in self._funding_graph.items():
            if wallet_address in funded_wallets:
                cluster.funding_sources.add(source)
                cluster.wallets.update(funded_wallets)
        
        return cluster
    
    async def get_recent_bundles(
        self,
        session: AsyncSession,
        limit: int = 20,
    ) -> List[BundleInfo]:
        """Get recently detected bundles."""
        bundles = list(self._detected_bundles.values())
        bundles.sort(key=lambda b: b.last_tx_time, reverse=True)
        return bundles[:limit]
    
    def get_bundle_priority(self, info: BundleInfo) -> AlertPriority:
        """Determine alert priority for a bundle."""
        if info.is_potential_rug:
            return AlertPriority.CRITICAL
        if info.coordination_score >= 90 and info.total_volume_sol >= 20:
            return AlertPriority.CRITICAL
        if info.coordination_score >= 80 or info.total_volume_sol >= 15:
            return AlertPriority.HIGH
        if info.coordination_score >= self.coordination_threshold:
            return AlertPriority.MEDIUM
        return AlertPriority.LOW
    
    async def format_bundle_alert(
        self,
        info: BundleInfo,
        token_symbol: str = None,
        token_name: str = None,
    ) -> str:
        """
        Format a bundle alert message in BBB style:
        
        Sol Bundles [BBB]
        MEN / 28 / 78.64%
        GgRVw7sjfKPRZvFLRXcL3XwtboA6oYfSX31pkQigvn1s
        4erEyY 1
        3w5Svr 1
        ...
        DT | PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        symbol = token_symbol or "???"
        name = token_name or ""
        
        # Build wallet breakdown
        wallet_lines = ""
        for w in info.wallet_breakdown[:28]:  # Show max 28 wallets
            short_addr = w.get("wallet", "")[:6]
            sol = w.get("sol", 0)
            # Format SOL to be human readable (avoid scientific notation)
            sol_str = f"{sol:.6f}".rstrip('0').rstrip('.') if sol < 1.0 else f"{sol:.4f}"
            if not sol_str or sol_str == "0":
                sol_str = "0.0000"
            wallet_lines += f"<a href=\"https://solscan.io/account/{w.get('wallet', '')}\">{short_addr}</a> {sol_str}\n"
        
        # Opening header
        header = "Sol Bundles"
        if info.is_opening_bundle:
            header = "📦 <b>SOL OPENING BUNDLE</b> 📦"
        
        # Get pair address for Axiom link
        from services.api_clients import get_token_fetcher
        pair_address = await get_token_fetcher().get_pair_address(info.token_address)
        if not pair_address:
            pair_address = info.token_address
        
        message = f"""{header}
{symbol} / {info.wallet_count} / {info.supply_percent:.2f}%
<code>{info.token_address}</code>
{wallet_lines}
<a href="https://trench.bot/buy/{info.token_address}">DT</a> | <a href="https://photon-sol.tinyastro.io/en/lp/{info.token_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={info.token_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={info.token_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{info.token_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={info.token_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={info.token_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={info.token_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={info.token_address}">NE</a> | <a href="https://pump.fun/{info.token_address}">PF</a>"""
        
        return message.strip()
    
    async def format_bundle_sale_alert(
        self,
        info: BundleInfo,
        token_symbol: str = None,
        token_name: str = None,
        market_cap_str: str = "?",
        coin_age_str: str = "?",
    ) -> str:
        """
        Format a bundle sale alert message in BBB style:
        
        SOL Bundle Sales [BBB]
        📦 $MEN MEN 2.33 30/16/1
        MC: 5.6m | CA: 3d | TS: 1.01
        GgRVw7sjfKPRZvFLRXcL3XwtboA6oYfSX31pkQigvn1s
        """
        symbol = token_symbol or "???"
        name = token_name or ""
        
        # Format: exits/partial/full
        exits_str = f"{info.total_exits}/{info.partial_exits}/{info.full_exits}"
        
        # Red dot if supply remains
        supply_emoji = "🔴" if info.supply_remaining > 0 else ""
        
        message = f"""SOL Bundle Sales
{supply_emoji}📦 ${symbol} {name} {info.total_volume_sol:.2f} {exits_str}
MC: {market_cap_str} | CA: {coin_age_str} | TS: {info.supply_remaining:.2f}
<code>{info.token_address}</code>"""
        
        return message.strip()
    
    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "tracked_tokens": len(self._recent_txs),
            "detected_bundles": len(self._detected_bundles),
            "wallet_clusters": len(self._funding_graph),
        }


# Singleton
_bundle_detector: BundleDetector | None = None


def get_bundle_detector() -> BundleDetector:
    """Get the singleton bundle detector."""
    global _bundle_detector
    if _bundle_detector is None:
        _bundle_detector = BundleDetector()
    return _bundle_detector
