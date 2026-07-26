"""Shared V2 domain contracts.

These models are deliberately chain-neutral so scanner commands, alerts,
simulation, replay tests, and the web mirror all speak the same language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Chain(str, Enum):
    """Supported V2 chains."""

    SOLANA = "sol"
    ETHEREUM = "eth"
    BSC = "bsc"
    BASE = "base"
    ROBINHOOD = "robinhood"

    @property
    def label(self) -> str:
        labels = {
            Chain.SOLANA: "SOL",
            Chain.ETHEREUM: "ETH",
            Chain.BSC: "BSC",
            Chain.BASE: "BASE",
            Chain.ROBINHOOD: "RH",
        }
        return labels[self]

    @classmethod
    def from_hint(cls, value: str) -> "Chain":
        normalized = value.strip().lower()
        aliases = {
            "solana": cls.SOLANA,
            "sol": cls.SOLANA,
            "ethereum": cls.ETHEREUM,
            "eth": cls.ETHEREUM,
            "bnb": cls.BSC,
            "bsc": cls.BSC,
            "base": cls.BASE,
            "rh": cls.ROBINHOOD,
            "robinhood": cls.ROBINHOOD,
            "robinhoodchain": cls.ROBINHOOD,
        }
        if normalized not in aliases:
            raise ValueError(f"Unsupported chain: {value}")
        return aliases[normalized]


class RiskLevel(str, Enum):
    """Human-readable risk buckets used by alerts and scans."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertKind(str, Enum):
    """Alert categories for topic routing."""

    OPPORTUNITY = "opportunity"
    RISK = "risk"
    FRESH = "fresh"
    DORMANT = "dormant"
    BUNDLE = "bundle"
    OPS = "ops"


class WalletLabel(str, Enum):
    """Behavior labels used for holder due diligence."""

    FRESH = "fresh"
    DORMANT = "dormant"
    BAD_DORMANT = "bad_dormant"
    MEV_BOT = "mev_bot"
    HIGH_VOLUME = "high_volume"
    TEAM_INSIDER = "team_insider"
    SNIPER = "sniper"
    SERIAL_RUGGER = "serial_rugger"
    SMART_MONEY = "smart_money"


@dataclass(slots=True)
class WalletProfile:
    """Normalized wallet metadata."""

    address: str
    age_days: Optional[int] = None
    inactive_days: Optional[int] = None
    tx_count: Optional[int] = None
    funding_source: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    current_token_holdings: Optional[int] = None
    portfolio_value_usd: Optional[float] = None
    pnl_usd: Optional[float] = None
    previous_tokens: list[str] = field(default_factory=list)
    previous_successful_tokens: int = 0
    previous_rugged_tokens: int = 0
    average_purchase_usd: Optional[float] = None
    average_hold_seconds: Optional[int] = None
    tokens_traded: Optional[int] = None
    first_seen_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    received_transfer_from: Optional[str] = None
    early_buy_seconds: Optional[int] = None


@dataclass(slots=True)
class HolderCluster:
    """Group of wallets that likely belong to one actor or behavior class."""

    label: str
    wallets: list[str]
    supply_percent: float
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RiskReport:
    """Risk facts collected from provider checks and local heuristics."""

    level: RiskLevel = RiskLevel.LOW
    is_honeypot: bool = False
    buy_tax_bps: Optional[int] = None
    sell_tax_bps: Optional[int] = None
    liquidity_locked: Optional[bool] = None
    delayed_honeypot: bool = False
    malicious_contract: bool = False
    liquidity_pull_risk: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SignalScore:
    """Balanced alert score.

    confidence and risk are normalized to 0-100. Higher confidence is better;
    higher risk is worse.
    """

    confidence: int = 0
    risk: int = 0
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.confidence = max(0, min(100, int(self.confidence)))
        self.risk = max(0, min(100, int(self.risk)))


@dataclass(slots=True)
class TokenScan:
    """One token report independent of chain/provider implementation."""

    chain: Chain
    address: str
    symbol: str
    name: str
    market_cap_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    created_at: Optional[datetime] = None
    creator: Optional[WalletProfile] = None
    holder_clusters: list[HolderCluster] = field(default_factory=list)
    risk: RiskReport = field(default_factory=RiskReport)
    signals: SignalScore = field(default_factory=SignalScore)
    fresh_wallet_buys: int = 0
    dormant_wallet_buys: int = 0
    bundle_supply_percent: float = 0.0
    social_score: int = 0
    is_pre_bonded: bool = False
    pool_type: Optional[str] = None
    source_urls: list[str] = field(default_factory=list)

    @property
    def primary_holder_cluster(self) -> Optional[HolderCluster]:
        if not self.holder_clusters:
            return None
        return max(self.holder_clusters, key=lambda cluster: cluster.supply_percent)


@dataclass(slots=True)
class AlertDecision:
    """Final routing decision for an alert candidate."""

    kind: AlertKind
    should_send: bool
    priority: str
    confidence: int
    risk: int
    reason: str
    topics: list[str] = field(default_factory=list)

    @classmethod
    def from_score(
        cls,
        kind: AlertKind,
        score: SignalScore,
        risk: RiskReport,
    ) -> "AlertDecision":
        if risk.is_honeypot:
            return cls(
                kind=kind,
                should_send=False,
                priority="blocked",
                confidence=score.confidence,
                risk=max(score.risk, 95),
                reason="Blocked: honeypot risk",
                topics=["risk"],
            )

        if risk.level is RiskLevel.CRITICAL or score.risk >= 90:
            return cls(
                kind=kind,
                should_send=False,
                priority="blocked",
                confidence=score.confidence,
                risk=score.risk,
                reason="Blocked: critical risk",
                topics=["risk"],
            )

        if score.confidence >= 85 and score.risk < 65:
            return cls(
                kind=kind,
                should_send=True,
                priority="high",
                confidence=score.confidence,
                risk=score.risk,
                reason="High confidence balanced signal",
                topics=[kind.value],
            )

        if score.confidence >= 65 and score.risk < 75:
            return cls(
                kind=kind,
                should_send=True,
                priority="medium",
                confidence=score.confidence,
                risk=score.risk,
                reason="Balanced signal",
                topics=[kind.value],
            )

        return cls(
            kind=kind,
            should_send=False,
            priority="low",
            confidence=score.confidence,
            risk=score.risk,
            reason="Insufficient confidence for balanced alert policy",
            topics=[],
        )


@dataclass(slots=True)
class WatchTarget:
    """A private watchlist target."""

    id: str
    chain: Chain
    address: str
    created_at: datetime
    note: Optional[str] = None


@dataclass(slots=True)
class ProviderHealth:
    """Provider status for the health contract."""

    name: str
    ok: bool
    rate_limited: bool = False
    detail: Optional[str] = None
    checked_at: Optional[datetime] = None


@dataclass(slots=True)
class SystemHealth:
    """V2 health snapshot that reflects useful work, not just process liveness."""

    ok: bool
    reasons: list[str]
    providers: list[ProviderHealth]
    ingestion_lag_seconds: Optional[float]
    queue_depth: int
    processed_events: int
