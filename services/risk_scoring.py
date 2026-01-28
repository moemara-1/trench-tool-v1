"""
Trench Tool V1 - Risk Scoring Engine
Calculates risk scores for wallets and tokens.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Wallet, Token, Freshie, WalletType, TradeAction

logger = logging.getLogger(__name__)


@dataclass
class WalletRiskScore:
    """Risk assessment for a wallet."""
    address: str
    total_score: float  # 0-100, higher = more risky
    
    # Component scores
    age_score: float  # Newer = riskier
    activity_score: float  # Low activity = riskier
    association_score: float  # Connected to scams = riskier
    pattern_score: float  # Suspicious patterns = riskier
    
    risk_level: str  # "low", "medium", "high", "critical"
    flags: list


@dataclass
class TokenRugScore:
    """Ruggability assessment for a token."""
    address: str
    total_score: float  # 0-100, higher = more likely to rug
    
    # Component scores
    liquidity_score: float  # Low liquidity = riskier
    holder_score: float  # Concentrated holders = riskier
    developer_score: float  # Dev holding lots = riskier
    contract_score: float  # Suspicious contract = riskier
    age_score: float  # Very new = riskier
    
    risk_level: str
    flags: list


@dataclass
class OpportunityScore:
    """Opportunity assessment combining multiple signals."""
    token_address: str
    total_score: float  # 0-100, higher = better opportunity
    
    # Component scores
    fresh_accumulation_score: float
    smart_money_score: float
    technical_score: float
    social_score: float
    liquidity_score: float
    
    recommendation: str  # "strong_buy", "buy", "watch", "avoid"


class RiskScoringEngine:
    """
    Calculates risk scores for wallets and tokens.
    
    Wallet Risk Score (0-100):
    - Age factor (newer = higher risk)
    - Transaction history (frequency/patterns)
    - Associated wallets (cluster analysis)
    - Previous token interactions
    - Known scam wallet database match
    
    Token Ruggability Score (0-100):
    - Liquidity depth
    - Developer holding %
    - Insider concentration
    - Lock status
    - Contract code analysis
    - Known honeypot patterns
    
    Opportunity Score (0-100):
    - Fresh wallet accumulation rate
    - Smart money entry signals
    - Technical strength indicators
    - Social momentum
    - Liquidity efficiency
    """
    
    def __init__(self):
        # Known scam addresses (would be loaded from database in production)
        self._known_scam_wallets: set = set()
        self._known_honeypots: set = set()
        
        # Cache scores to avoid recalculation
        self._wallet_scores: Dict[str, WalletRiskScore] = {}
        self._token_scores: Dict[str, TokenRugScore] = {}
    
    # ==================== WALLET RISK SCORING ====================
    
    def calculate_wallet_risk_score(
        self,
        wallet: Wallet,
        transaction_count: int = None,
        associated_scam_count: int = 0,
    ) -> WalletRiskScore:
        """Calculate risk score for a wallet."""
        flags = []
        
        # Age Score (0-30) - Newer wallets are riskier
        if wallet.first_activity_at:
            wallet_age_days = (datetime.utcnow() - wallet.first_activity_at).days
            if wallet_age_days < 1:
                age_score = 30
                flags.append("brand_new_wallet")
            elif wallet_age_days < 7:
                age_score = 25
                flags.append("fresh_wallet")
            elif wallet_age_days < 30:
                age_score = 15
            elif wallet_age_days < 90:
                age_score = 8
            else:
                age_score = 0
        else:
            age_score = 30
            flags.append("no_history")
        
        # Activity Score (0-25) - Low activity is suspicious
        tx_count = transaction_count or wallet.total_transactions
        if tx_count == 0:
            activity_score = 25
            flags.append("no_transactions")
        elif tx_count < 5:
            activity_score = 20
            flags.append("low_activity")
        elif tx_count < 20:
            activity_score = 10
        elif tx_count > 1000:
            activity_score = 15  # Could be a bot
            flags.append("possible_bot")
        else:
            activity_score = 0
        
        # Association Score (0-25) - Connected to known scams
        if wallet.address in self._known_scam_wallets:
            association_score = 25
            flags.append("known_scammer")
        elif associated_scam_count > 5:
            association_score = 20
            flags.append("scam_associated")
        elif associated_scam_count > 0:
            association_score = associated_scam_count * 4
            flags.append("minor_scam_association")
        else:
            association_score = 0
        
        # Pattern Score (0-20) - Suspicious trading patterns
        pattern_score = 0
        if wallet.wallet_type == WalletType.FRESH:
            pattern_score += 5
        if wallet.wallet_type == WalletType.DORMANT:
            pattern_score += 10
            flags.append("dormant_wallet")
        
        # Total Score
        total_score = min(100, age_score + activity_score + association_score + pattern_score)
        
        # Risk Level
        if total_score >= 75:
            risk_level = "critical"
        elif total_score >= 50:
            risk_level = "high"
        elif total_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        score = WalletRiskScore(
            address=wallet.address,
            total_score=total_score,
            age_score=age_score,
            activity_score=activity_score,
            association_score=association_score,
            pattern_score=pattern_score,
            risk_level=risk_level,
            flags=flags,
        )
        
        self._wallet_scores[wallet.address] = score
        return score
    
    # ==================== TOKEN RUG SCORING ====================
    
    def calculate_token_rug_score(
        self,
        token: Token,
        liquidity_usd: float = None,
        top_holder_percent: float = None,
        dev_holding_percent: float = None,
        is_locked: bool = False,
    ) -> TokenRugScore:
        """Calculate ruggability score for a token."""
        flags = []
        
        # Liquidity Score (0-25) - Low liquidity = easy to rug
        liq = liquidity_usd or token.liquidity_usd or 0
        if liq < 1000:
            liquidity_score = 25
            flags.append("ultra_low_liquidity")
        elif liq < 5000:
            liquidity_score = 20
            flags.append("low_liquidity")
        elif liq < 20000:
            liquidity_score = 12
        elif liq < 100000:
            liquidity_score = 5
        else:
            liquidity_score = 0
        
        # Holder Score (0-25) - Concentrated = risky
        top_holder = top_holder_percent or 0
        if top_holder > 50:
            holder_score = 25
            flags.append("majority_holder")
        elif top_holder > 30:
            holder_score = 18
            flags.append("concentrated_supply")
        elif top_holder > 15:
            holder_score = 10
        else:
            holder_score = 0
        
        # Developer Score (0-20) - Dev holding = rug risk
        dev_holding = dev_holding_percent or 0
        if dev_holding > 30:
            developer_score = 20
            flags.append("dev_owns_supply")
        elif dev_holding > 15:
            developer_score = 12
            flags.append("large_dev_holding")
        elif dev_holding > 5:
            developer_score = 5
        else:
            developer_score = 0
        
        # Age Score (0-15) - Very new = risky
        if token.first_seen_at:
            token_age_hours = (datetime.utcnow() - token.first_seen_at).total_seconds() / 3600
            if token_age_hours < 1:
                age_score = 15
                flags.append("brand_new_token")
            elif token_age_hours < 24:
                age_score = 10
                flags.append("new_token")
            elif token_age_hours < 72:
                age_score = 5
            else:
                age_score = 0
        else:
            age_score = 10
        
        # Contract Score (0-15) - Locked reduces risk
        if is_locked:
            contract_score = 0
            flags.append("liquidity_locked")
        elif token.address in self._known_honeypots:
            contract_score = 15
            flags.append("known_honeypot")
        else:
            contract_score = 8  # Unknown contract
        
        # Total Score
        total_score = min(100, liquidity_score + holder_score + developer_score + age_score + contract_score)
        
        # Risk Level
        if total_score >= 75:
            risk_level = "critical"
        elif total_score >= 50:
            risk_level = "high"
        elif total_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        score = TokenRugScore(
            address=token.contract_address,
            total_score=total_score,
            liquidity_score=liquidity_score,
            holder_score=holder_score,
            developer_score=developer_score,
            contract_score=contract_score,
            age_score=age_score,
            risk_level=risk_level,
            flags=flags,
        )
        
        self._token_scores[token.contract_address] = score
        return score
    
    # ==================== OPPORTUNITY SCORING ====================
    
    async def calculate_opportunity_score(
        self,
        session: AsyncSession,
        token: Token,
        fresh_buy_count: int = 0,
        smart_money_entries: int = 0,
    ) -> OpportunityScore:
        """Calculate opportunity score based on multiple signals."""
        
        # Fresh Accumulation (0-30)
        if fresh_buy_count >= 20:
            fresh_score = 30
        elif fresh_buy_count >= 10:
            fresh_score = 25
        elif fresh_buy_count >= 5:
            fresh_score = 18
        elif fresh_buy_count >= 2:
            fresh_score = 10
        else:
            fresh_score = 0
        
        # Smart Money (0-25)
        if smart_money_entries >= 5:
            smart_score = 25
        elif smart_money_entries >= 3:
            smart_score = 18
        elif smart_money_entries >= 1:
            smart_score = 10
        else:
            smart_score = 0
        
        # Technical/Age (0-20) - Sweet spot is not too new, not too old
        if token.first_seen_at:
            age_hours = (datetime.utcnow() - token.first_seen_at).total_seconds() / 3600
            if 1 <= age_hours <= 24:
                technical_score = 20  # Sweet spot
            elif 24 < age_hours <= 72:
                technical_score = 15
            elif age_hours < 1:
                technical_score = 5  # Too new, risky
            else:
                technical_score = 8
        else:
            technical_score = 10
        
        # Social - Placeholder (0-15)
        social_score = 0
        
        # Liquidity Efficiency (0-10)
        if token.liquidity_usd and token.market_cap:
            liq_ratio = token.liquidity_usd / token.market_cap
            if liq_ratio > 0.2:
                liquidity_score = 10
            elif liq_ratio > 0.1:
                liquidity_score = 7
            elif liq_ratio > 0.05:
                liquidity_score = 4
            else:
                liquidity_score = 0
        else:
            liquidity_score = 0
        
        total_score = fresh_score + smart_score + technical_score + social_score + liquidity_score
        
        # Recommendation
        if total_score >= 70:
            recommendation = "strong_buy"
        elif total_score >= 50:
            recommendation = "buy"
        elif total_score >= 30:
            recommendation = "watch"
        else:
            recommendation = "avoid"
        
        return OpportunityScore(
            token_address=token.contract_address,
            total_score=total_score,
            fresh_accumulation_score=fresh_score,
            smart_money_score=smart_score,
            technical_score=technical_score,
            social_score=social_score,
            liquidity_score=liquidity_score,
            recommendation=recommendation,
        )
    
    def add_known_scam_wallet(self, address: str):
        """Add a wallet to the known scammers list."""
        self._known_scam_wallets.add(address)
    
    def add_known_honeypot(self, address: str):
        """Add a token to the known honeypots list."""
        self._known_honeypots.add(address)
    
    def get_stats(self) -> dict:
        """Get engine statistics."""
        return {
            "cached_wallet_scores": len(self._wallet_scores),
            "cached_token_scores": len(self._token_scores),
            "known_scam_wallets": len(self._known_scam_wallets),
            "known_honeypots": len(self._known_honeypots),
        }


# Singleton
_risk_engine: RiskScoringEngine | None = None


def get_risk_engine() -> RiskScoringEngine:
    """Get the singleton risk scoring engine."""
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskScoringEngine()
    return _risk_engine
