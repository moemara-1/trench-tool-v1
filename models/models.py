"""
Trench Tool V1 - Database Models
SQLAlchemy models for tokens, wallets, freshies, and alerts.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, 
    ForeignKey, Text, JSON, BigInteger, Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import ARRAY
from pydantic import BaseModel
import enum


# SQLAlchemy Base
class Base(DeclarativeBase):
    pass


# Enums
class WalletType(str, enum.Enum):
    FRESH = "fresh"
    DORMANT = "dormant"
    ACTIVE = "active"
    EXCHANGE = "exchange"
    BOT = "bot"
    WHALE = "whale"


class AlertPriority(str, enum.Enum):
    CRITICAL = "critical"  # 🔴
    HIGH = "high"          # 🟠
    MEDIUM = "medium"      # 🟡
    LOW = "low"            # 🟢


class TradeAction(str, enum.Enum):
    BUY = "buy"
    PARTIAL_SELL = "partial_sell"
    FULL_SELL = "full_sell"


# SQLAlchemy Models
class Token(Base):
    """Token/coin information."""
    __tablename__ = "tokens"
    
    contract_address = Column(String(64), primary_key=True)
    chain = Column(String(20), default="solana")
    name = Column(String(100), nullable=True)
    symbol = Column(String(20), nullable=True)
    decimals = Column(Integer, default=9)
    created_at = Column(DateTime, default=datetime.utcnow)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    
    # Market data (updated periodically)
    market_cap = Column(Float, nullable=True)
    price_usd = Column(Float, nullable=True)
    liquidity_usd = Column(Float, nullable=True)
    volume_24h = Column(Float, nullable=True)
    
    # Launchpad info
    launchpad = Column(String(50), nullable=True)  # pump.fun, meteora, raydium, etc.
    
    # Risk scoring
    rug_score = Column(Float, default=0.0)  # 0-100, higher = more risky
    
    # Relationships
    freshies = relationship("Freshie", back_populates="token")
    alerts = relationship("Alert", back_populates="token")


class Wallet(Base):
    """Wallet information and classification."""
    __tablename__ = "wallets"
    
    address = Column(String(64), primary_key=True)
    chain = Column(String(20), default="solana")
    
    # Timestamps
    first_activity_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Classification
    wallet_type = Column(SQLEnum(WalletType), default=WalletType.ACTIVE)
    label = Column(String(100), nullable=True)  # Custom label
    
    # Metrics
    total_transactions = Column(Integer, default=0)
    total_volume_sol = Column(Float, default=0.0)
    
    # Risk scoring
    risk_score = Column(Float, default=0.0)  # 0-100
    
    # Funding source tracking
    funding_source = Column(String(100), nullable=True)
    funding_timestamp = Column(DateTime, nullable=True)
    
    # Relationships
    freshies = relationship("Freshie", back_populates="wallet")
    alerts = relationship("Alert", back_populates="wallet")


class Freshie(Base):
    """Fresh wallet token purchase event."""
    __tablename__ = "freshies"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # Foreign keys
    wallet_address = Column(String(64), ForeignKey("wallets.address"))
    token_address = Column(String(64), ForeignKey("tokens.contract_address"))
    
    # Transaction details
    tx_signature = Column(String(128), unique=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Purchase info
    amount_sol = Column(Float)
    amount_tokens = Column(Float, nullable=True)
    price_at_purchase = Column(Float, nullable=True)
    
    # Classification
    action = Column(SQLEnum(TradeAction), default=TradeAction.BUY)
    is_first_mention = Column(Boolean, default=False)  # ⭐️
    
    # Indicators (JSON for flexibility)
    indicators = Column(JSON, default=dict)  # Emojis, router, launchpad, etc.
    
    # Current status
    current_holding = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    
    # Relationships
    wallet = relationship("Wallet", back_populates="freshies")
    token = relationship("Token", back_populates="freshies")


class Alert(Base):
    """Alert sent to Telegram."""
    __tablename__ = "alerts"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # Foreign keys
    token_address = Column(String(64), ForeignKey("tokens.contract_address"), nullable=True)
    wallet_address = Column(String(64), ForeignKey("wallets.address"), nullable=True)
    
    # Alert info
    alert_type = Column(String(50))  # freshie, dormant, bundle, etc.
    priority = Column(SQLEnum(AlertPriority), default=AlertPriority.MEDIUM)
    
    # Content
    message = Column(Text)
    indicators = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    
    # Status
    telegram_message_id = Column(BigInteger, nullable=True)
    
    # Relationships
    token = relationship("Token", back_populates="alerts")
    wallet = relationship("Wallet", back_populates="alerts")


# Pydantic Models for API responses
class TokenResponse(BaseModel):
    contract_address: str
    chain: str
    name: Optional[str]
    symbol: Optional[str]
    market_cap: Optional[float]
    price_usd: Optional[float]
    liquidity_usd: Optional[float]
    launchpad: Optional[str]
    rug_score: float
    
    class Config:
        from_attributes = True


class WalletResponse(BaseModel):
    address: str
    chain: str
    wallet_type: WalletType
    first_activity_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    total_transactions: int
    risk_score: float
    funding_source: Optional[str]
    
    class Config:
        from_attributes = True


class FreshieResponse(BaseModel):
    id: int
    wallet_address: str
    token_address: str
    tx_signature: str
    timestamp: datetime
    amount_sol: float
    action: TradeAction
    is_first_mention: bool
    indicators: dict
    
    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: int
    alert_type: str
    priority: AlertPriority
    message: str
    created_at: datetime
    token_address: Optional[str]
    wallet_address: Optional[str]
    
    class Config:
        from_attributes = True
