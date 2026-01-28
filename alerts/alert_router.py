"""
Trench Tool V1 - Alert Router
Routes alerts to appropriate channels based on priority and type.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import cache_get, cache_set, is_rate_limited
from models import Alert, AlertPriority
from .telegram_bot import get_telegram_bot, TelegramAlertBot

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes and manages alert delivery."""
    
    def __init__(self, telegram_bot: TelegramAlertBot = None):
        self.telegram = telegram_bot or get_telegram_bot()
        self._alert_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
    
    async def should_send_alert(
        self,
        token_address: str,
        alert_type: str,
    ) -> bool:
        """
        Check if we should send this alert (rate limiting).
        
        Prevents spam by limiting duplicate alerts for the same token.
        """
        cache_key = f"alert:{alert_type}:{token_address}"
        
        # Check cooldown
        is_limited = await is_rate_limited(
            key=cache_key,
            limit=1,
            window_seconds=settings.alert_cooldown_seconds,
        )
        
        if is_limited:
            logger.debug(f"Rate limited alert for {token_address}")
            return False
        
        return True
    
    async def route_alert(
        self,
        session: AsyncSession,
        alert_type: str,
        priority: AlertPriority,
        message: str,
        token_address: Optional[str] = None,
        wallet_address: Optional[str] = None,
        indicators: dict = None,
    ) -> Optional[Alert]:
        """
        Route an alert to the appropriate channel and save to database.
        
        Returns the created Alert object if successful.
        """
        # Check rate limit
        if token_address:
            should_send = await self.should_send_alert(token_address, alert_type)
            if not should_send:
                return None
        
        # Send to Telegram
        message_id = await self.telegram.send_alert(
            message=message,
            disable_notification=(priority == AlertPriority.LOW),
        )
        
        # Create database record
        alert = Alert(
            alert_type=alert_type,
            priority=priority,
            message=message,
            token_address=token_address,
            wallet_address=wallet_address,
            indicators=indicators or {},
            sent_at=datetime.utcnow() if message_id else None,
            telegram_message_id=message_id,
        )
        
        session.add(alert)
        
        # Update counts
        self._alert_counts[priority.value] += 1
        
        logger.info(
            f"Routed {priority.value} {alert_type} alert for token {token_address}"
        )
        
        return alert
    
    async def send_freshie_alert(
        self,
        session: AsyncSession,
        ticker: str,
        token_name: str,
        contract_address: str,
        wallet_address: str,
        amount_sol: float,
        market_cap: Optional[float],
        coin_age_minutes: int,
        indicators: dict,
        priority: AlertPriority,
        **kwargs,
    ) -> Optional[Alert]:
        """Send a freshie alert through the routing system."""
        
        # Check rate limit
        should_send = await self.should_send_alert(contract_address, "freshie")
        if not should_send:
            return None
        
        # Format message
        message = await self.telegram.format_freshie_alert(
            ticker=ticker,
            token_name=token_name,
            contract_address=contract_address,
            wallet_address=wallet_address,
            amount_sol=amount_sol,
            market_cap=market_cap,
            coin_age_minutes=coin_age_minutes,
            indicators=indicators,
            priority=priority,
            **kwargs,
        )
        
        # Send via Telegram
        message_id = await self.telegram.send_alert(
            message=message,
            disable_notification=(priority == AlertPriority.LOW),
        )
        
        # Create database record
        alert = Alert(
            alert_type="freshie",
            priority=priority,
            message=message,
            token_address=contract_address,
            wallet_address=wallet_address,
            indicators=indicators,
            sent_at=datetime.utcnow() if message_id else None,
            telegram_message_id=message_id,
        )
        
        session.add(alert)
        self._alert_counts[priority.value] += 1
        
        return alert
    
    def get_stats(self) -> dict:
        """Get alert statistics."""
        return {
            "total_alerts": sum(self._alert_counts.values()),
            "by_priority": self._alert_counts.copy(),
        }


# Singleton
_alert_router: AlertRouter | None = None


def get_alert_router() -> AlertRouter:
    """Get the singleton alert router."""
    global _alert_router
    if _alert_router is None:
        _alert_router = AlertRouter()
    return _alert_router
