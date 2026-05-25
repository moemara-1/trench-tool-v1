"""
Trench Tool V1 - Freshies Tracker Service
Core service for tracking fresh wallet token purchases.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import Token, Wallet, Freshie, WalletType, TradeAction, AlertPriority
from filters import TransactionFilter, TransactionIndicators, get_transaction_filter
from alerts import get_alert_router

logger = logging.getLogger(__name__)


class FreshiesTracker:
    """Tracks and processes fresh wallet token purchases."""
    
    def __init__(self):
        self.filter = get_transaction_filter()
        self.alert_router = get_alert_router()
        
        # Metrics
        self._processed_count = 0
        self._fresh_buy_count = 0
        self._alert_count = 0
    
    async def get_or_create_token(
        self,
        session: AsyncSession,
        contract_address: str,
        name: str = None,
        symbol: str = None,
        launchpad: str = None,
    ) -> Token:
        """Get existing token or create new one."""
        result = await session.execute(
            select(Token).where(Token.contract_address == contract_address)
        )
        token = result.scalar_one_or_none()
        
        if token:
            return token
        
        token = Token(
            contract_address=contract_address,
            name=name or "Unknown",
            symbol=symbol or "???",
            launchpad=launchpad,
            first_seen_at=datetime.utcnow(),
        )
        session.add(token)
        return token
    
    async def get_bbb_metrics(
        self,
        session: AsyncSession,
        token_address: str,
    ) -> dict:
        """
        Get BBB-style metrics for a token.
        
        Returns counts of:
        - Fresh wallet buys
        - Fresh wallet full sells
        - Fresh wallet partial sells
        - Dormant wallet buys
        """
        # Fresh buys
        fresh_buys = await session.execute(
            select(func.count(Freshie.id))
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                Freshie.token_address == token_address,
                Freshie.action == TradeAction.BUY,
                Wallet.wallet_type == WalletType.FRESH,
            )
        )
        fresh_buy_count = fresh_buys.scalar() or 0
        
        # Full sells
        full_sells = await session.execute(
            select(func.count(Freshie.id))
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                Freshie.token_address == token_address,
                Freshie.action == TradeAction.FULL_SELL,
                Wallet.wallet_type == WalletType.FRESH,
            )
        )
        full_sell_count = full_sells.scalar() or 0
        
        # Partial sells
        partial_sells = await session.execute(
            select(func.count(Freshie.id))
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                Freshie.token_address == token_address,
                Freshie.action == TradeAction.PARTIAL_SELL,
                Wallet.wallet_type == WalletType.FRESH,
            )
        )
        partial_sell_count = partial_sells.scalar() or 0
        
        # Dormant buys
        dormant_buys = await session.execute(
            select(func.count(Freshie.id))
            .join(Wallet, Freshie.wallet_address == Wallet.address)
            .where(
                Freshie.token_address == token_address,
                Freshie.action == TradeAction.BUY,
                Wallet.wallet_type == WalletType.DORMANT,
            )
        )
        dormant_buy_count = dormant_buys.scalar() or 0
        
        return {
            "fresh_buy_count": fresh_buy_count,
            "fresh_sell_count": full_sell_count,
            "partial_sell_count": partial_sell_count,
            "dormant_buy_count": dormant_buy_count,
        }
    
    async def process_token_purchase(
        self,
        session: AsyncSession,
        wallet: Wallet,
        token: Token,
        tx_signature: str,
        amount_sol: float,
        amount_tokens: float = None,
        program_ids: list[str] = None,
        suppress_alert: bool = False,
    ) -> Optional[Freshie]:
        """
        Process a token purchase transaction.
        
        Creates a Freshie record and sends alert if appropriate.
        
        Returns the created Freshie if alert-worthy.
        """
        self._processed_count += 1
        program_ids = program_ids or []
        
        # Skip if below minimum
        if amount_sol < settings.min_transaction_sol:
            return None
            
        # Check if transaction already exists
        existing = await session.execute(
            select(Freshie).where(Freshie.tx_signature == tx_signature)
        )
        if existing.scalar_one_or_none():
            # Already processed
            return None
        
        # Get indicators
        indicators = self.filter.analyze_transaction(
            amount_sol=amount_sol,
            program_ids=program_ids,
            token_address=token.contract_address,
            wallet_type=wallet.wallet_type.value,
        )
        
        # Create Freshie record
        freshie = Freshie(
            wallet_address=wallet.address,
            token_address=token.contract_address,
            tx_signature=tx_signature,
            amount_sol=amount_sol,
            amount_tokens=amount_tokens,
            action=TradeAction.BUY,
            is_first_mention=indicators.is_first_mention,
            indicators=indicators.to_dict(),
        )
        session.add(freshie)
        
        # Track fresh buys
        if wallet.wallet_type == WalletType.FRESH:
            self._fresh_buy_count += 1
        
        # Check if we should alert
        should_alert = self.filter.should_alert(
            amount_sol=amount_sol,
            wallet_type=wallet.wallet_type.value,
            indicators=indicators,
        )
        
        if should_alert and not suppress_alert:
            await self._send_alert(
                session=session,
                token=token,
                wallet=wallet,
                freshie=freshie,
                amount_sol=amount_sol,
                indicators=indicators,
            )
            self._alert_count += 1
        
        # If we suppressed the alert, we still return the freshie if it WAS alert-worthy
        # This allows the caller to know it qualified
        return freshie if should_alert else None
        
    async def process_token_sell(
        self,
        session: AsyncSession,
        wallet: Wallet,
        token: Token,
        tx_signature: str,
        amount_tokens: float,
        is_full_sell: bool = False,
        suppress_alert: bool = False,
    ) -> Optional[Freshie]:
        """
        Process a token sell transaction.
        Tracks partial vs full sells.
        """
        # Check if transaction already exists
        existing = await session.execute(
            select(Freshie).where(Freshie.tx_signature == tx_signature)
        )
        if existing.scalar_one_or_none():
            return None
        
        action = TradeAction.FULL_SELL if is_full_sell else TradeAction.PARTIAL_SELL
        
        # Create record
        freshie = Freshie(
            wallet_address=wallet.address,
            token_address=token.contract_address,
            tx_signature=tx_signature,
            amount_sol=0, # Sell doesn't spend SOL (usually)
            amount_tokens=amount_tokens,
            action=action,
            is_first_mention=False,
            indicators={},
        )
        session.add(freshie)
        
        # We don't typically alert on individual sells via this method (SolanaListener handles it)
        # But we return it so the caller knows it was recorded
        return freshie
    
    async def _send_alert(
        self,
        session: AsyncSession,
        token: Token,
        wallet: Wallet,
        freshie: Freshie,
        amount_sol: float,
        indicators: TransactionIndicators,
    ):
        """Send alert for a freshie event."""
        # Get BBB metrics
        metrics = await self.get_bbb_metrics(session, token.contract_address)
        
        # Calculate coin age
        if token.first_seen_at:
            coin_age = datetime.utcnow() - token.first_seen_at
            coin_age_minutes = int(coin_age.total_seconds() / 60)
        else:
            coin_age_minutes = 0
        
        # Determine priority
        priority_str = self.filter.get_alert_priority(
            amount_sol=amount_sol,
            wallet_type=wallet.wallet_type.value,
            indicators=indicators,
        )
        priority = AlertPriority(priority_str)
        
        # Send alert
        await self.alert_router.send_freshie_alert(
            session=session,
            ticker=token.symbol or "???",
            token_name=token.name or "Unknown",
            contract_address=token.contract_address,
            wallet_address=wallet.address,
            amount_sol=amount_sol,
            market_cap=token.market_cap,
            coin_age_minutes=coin_age_minutes,
            indicators=indicators.to_dict(),
            priority=priority,
            funding_source=wallet.funding_source or "Unknown",
            funding_time=wallet.funding_timestamp.strftime("%H:%M") if wallet.funding_timestamp else "Unknown",
            **metrics,
        )
    
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "processed_transactions": self._processed_count,
            "fresh_buys": self._fresh_buy_count,
            "alerts_sent": self._alert_count,
        }


# Singleton
_freshies_tracker: FreshiesTracker | None = None


def get_freshies_tracker() -> FreshiesTracker:
    """Get the singleton freshies tracker."""
    global _freshies_tracker
    if _freshies_tracker is None:
        _freshies_tracker = FreshiesTracker()
    return _freshies_tracker
