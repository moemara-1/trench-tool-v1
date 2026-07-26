"""Conservative live signal worker for V2 Telegram topics."""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol

from best_signals import BestSignalCandidate, BestSignalRouter, format_best_signal
from quality_budget import PriorityDailyBudget
from trench_v2.config import V2Settings
from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.engine.backtest import load_performance_profiles
from trench_v2.engine.signal_journal import SignalJournal
from trench_v2.providers.base import RiskProvider
from trench_v2.providers.dexscreener import DexPair, DexScreenerProvider, DexTokenProfile
from trench_v2.providers.factory import build_risk_provider
from trench_v2.providers.wallet_performance import MoralisTopTradersProvider
from trench_v2.telegram.sender import BotApiTelegramSender, TelegramSender
from trench_v2.telegram.topics import TopicFeature, topic_env_key
from wallet_performance import (
    WalletPerformanceCandidate,
    best_signal_from_wallet_token_confluence,
    score_wallet_token_confluence,
    wallet_token_confluence_rejection_reason,
)

logger = logging.getLogger(__name__)

_BEST_WALLET_CONFLUENCE_TOPIC_ENV = "TELEGRAM_BEST_WALLET_CONFLUENCE_TOPIC_ID"

_BEST_WALLET_TOPIC_ENV_BY_PERIOD = {
    "week": "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID",
    "month": "TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID",
    "year": "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID",
}

_MAX_PENDING_BEST_RECHECKS = 100
_MAX_BEST_RECHECK_ATTEMPTS = 12
_BEST_RECHECKS_PER_RUN = 25


class DiscoveryProvider(Protocol):
    async def latest_profiles(self) -> list[DexTokenProfile]:
        """Return latest token profiles."""

    async def best_pair(self, profile: DexTokenProfile) -> DexPair | None:
        """Return the best pair for a token profile."""


class WalletPerformanceProvider(Protocol):
    async def best_wallets_for_token(
        self,
        *,
        chain: Chain,
        token_address: str,
        token_symbol: str,
        periods: tuple[str, ...],
    ) -> list[WalletPerformanceCandidate]:
        """Return verified top-wallet candidates for the token."""


@dataclass(frozen=True, slots=True)
class LiveSignal:
    chain: Chain
    feature: TopicFeature
    topic_env_key: str
    token_address: str
    symbol: str
    name: str
    price_usd: float | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    buys_5m: int
    buys_1h: int
    buys_24h: int
    sells_5m: int
    sells_1h: int
    sells_24h: int
    pair_age_minutes: int | None
    price_change_5m: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    url: str | None
    reasons: tuple[str, ...]
    quality_score: int
    risk_level: RiskLevel | None = None
    buy_tax_bps: int | None = None
    sell_tax_bps: int | None = None
    risk_reasons: tuple[str, ...] = ()

    @property
    def dedupe_key(self) -> str:
        return f"{self.topic_env_key}:{self.chain.value}:{self.token_address.lower()}"


@dataclass(slots=True)
class LiveSignalStats:
    running: bool = False
    last_run_at: datetime | None = None
    last_error: str | None = None
    profiles_seen: int = 0
    pair_lookup_failures: int = 0
    candidates_seen: int = 0
    rejected_low_quality: int = 0
    rejected_low_quality_by_reason: dict[str, int] = field(default_factory=dict)
    last_low_quality_rejections: list[dict] = field(default_factory=list)
    alerts_sent: int = 0
    delivery_failures: int = 0
    delivery_failures_by_topic: dict[str, int] = field(default_factory=dict)
    deduped: int = 0
    daily_sent: int = 0
    rejected_daily_budget: int = 0
    risk_checked: int = 0
    risk_lookup_failures: int = 0
    rejected_risk: int = 0
    best_signals_sent: int = 0
    best_signal_candidates_seen: int = 0
    best_signal_skipped_by_reason: dict[str, int] = field(default_factory=dict)
    pending_best_confluence: int = 0
    pending_best_signal_rechecks: int = 0
    best_wallet_tokens_checked: int = 0
    best_wallet_provider_empty: int = 0
    best_wallet_candidates_seen: int = 0
    best_wallet_signals_sent: int = 0
    best_wallet_signals_queued: int = 0
    best_wallet_last_error: str | None = None
    journal_records_written: int = 0
    journal_last_error: str | None = None
    best_signal_journal_records_written: int = 0
    best_signal_journal_last_error: str | None = None
    hydrated_dedupe_keys: int = 0
    best_signal_rejected_by_reason: dict[str, int] = field(default_factory=dict)
    best_wallet_candidates_by_period: dict[str, int] = field(default_factory=dict)
    best_wallet_rejected_by_period: dict[str, int] = field(default_factory=dict)
    best_wallet_rejected_by_reason: dict[str, int] = field(default_factory=dict)
    best_wallet_last_score_by_period: dict[str, int] = field(default_factory=dict)
    candidates_by_topic: dict[str, int] = field(default_factory=dict)
    skipped_unconfigured_by_topic: dict[str, int] = field(default_factory=dict)
    alerts_by_topic: dict[str, int] = field(default_factory=dict)
    rejected_budget_by_topic: dict[str, int] = field(default_factory=dict)
    rejected_risk_by_topic: dict[str, int] = field(default_factory=dict)
    rejected_risk_by_topic_reason: dict[str, int] = field(default_factory=dict)
    last_risk_rejections: list[dict] = field(default_factory=list)
    alerts_by_quality_band: dict[str, int] = field(default_factory=dict)
    last_signals: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "profiles_seen": self.profiles_seen,
            "pair_lookup_failures": self.pair_lookup_failures,
            "candidates_seen": self.candidates_seen,
            "rejected_low_quality": self.rejected_low_quality,
            "rejected_low_quality_by_reason": dict(sorted(self.rejected_low_quality_by_reason.items())),
            "last_low_quality_rejections": self.last_low_quality_rejections[-10:],
            "alerts_sent": self.alerts_sent,
            "delivery_failures": self.delivery_failures,
            "delivery_failures_by_topic": dict(sorted(self.delivery_failures_by_topic.items())),
            "deduped": self.deduped,
            "daily_sent": self.daily_sent,
            "rejected_daily_budget": self.rejected_daily_budget,
            "risk_checked": self.risk_checked,
            "risk_lookup_failures": self.risk_lookup_failures,
            "rejected_risk": self.rejected_risk,
            "best_signals_sent": self.best_signals_sent,
            "best_signal_candidates_seen": self.best_signal_candidates_seen,
            "best_signal_skipped_by_reason": dict(sorted(self.best_signal_skipped_by_reason.items())),
            "pending_best_confluence": self.pending_best_confluence,
            "pending_best_signal_rechecks": self.pending_best_signal_rechecks,
            "best_wallet_tokens_checked": self.best_wallet_tokens_checked,
            "best_wallet_provider_empty": self.best_wallet_provider_empty,
            "best_wallet_candidates_seen": self.best_wallet_candidates_seen,
            "best_wallet_signals_sent": self.best_wallet_signals_sent,
            "best_wallet_signals_queued": self.best_wallet_signals_queued,
            "best_wallet_last_error": self.best_wallet_last_error,
            "journal_records_written": self.journal_records_written,
            "journal_last_error": self.journal_last_error,
            "best_signal_journal_records_written": self.best_signal_journal_records_written,
            "best_signal_journal_last_error": self.best_signal_journal_last_error,
            "hydrated_dedupe_keys": self.hydrated_dedupe_keys,
            "best_signal_rejected_by_reason": dict(sorted(self.best_signal_rejected_by_reason.items())),
            "best_wallet_candidates_by_period": dict(sorted(self.best_wallet_candidates_by_period.items())),
            "best_wallet_rejected_by_period": dict(sorted(self.best_wallet_rejected_by_period.items())),
            "best_wallet_rejected_by_reason": dict(sorted(self.best_wallet_rejected_by_reason.items())),
            "best_wallet_last_score_by_period": dict(sorted(self.best_wallet_last_score_by_period.items())),
            "candidates_by_topic": dict(sorted(self.candidates_by_topic.items())),
            "skipped_unconfigured_by_topic": dict(sorted(self.skipped_unconfigured_by_topic.items())),
            "alerts_by_topic": dict(sorted(self.alerts_by_topic.items())),
            "rejected_budget_by_topic": dict(sorted(self.rejected_budget_by_topic.items())),
            "rejected_risk_by_topic": dict(sorted(self.rejected_risk_by_topic.items())),
            "rejected_risk_by_topic_reason": dict(sorted(self.rejected_risk_by_topic_reason.items())),
            "last_risk_rejections": self.last_risk_rejections[-10:],
            "alerts_by_quality_band": dict(sorted(self.alerts_by_quality_band.items())),
            "last_signals": self.last_signals[-10:],
        }


class LiveSignalWorker:
    """Poll latest token profiles and send low-noise topic alerts."""

    _CHAIN_MAX_MC = {
        Chain.ETHEREUM: 500_000_000,
        Chain.BASE: 25_000_000,
        Chain.BSC: 500_000_000,
        Chain.ROBINHOOD: 250_000_000,
    }

    def __init__(
        self,
        settings: V2Settings,
        provider: DiscoveryProvider | None = None,
        sender: TelegramSender | None = None,
        risk_provider: RiskProvider | None = None,
        best_signal_router: BestSignalRouter | None = None,
        wallet_performance_provider: WalletPerformanceProvider | None = None,
    ):
        self.settings = settings
        self.provider = provider or DexScreenerProvider()
        self.sender = sender or self._sender_from_settings(settings)
        self.risk_provider = risk_provider or build_risk_provider(settings)
        self.wallet_performance_provider = wallet_performance_provider or self._wallet_provider_from_settings(settings)
        self.stats = LiveSignalStats()
        self.signal_journal = SignalJournal(settings.signal_journal_path) if settings.signal_journal_path else None
        self._daily_budget = (
            PriorityDailyBudget(
                daily_cap=settings.signal_daily_cap,
                min_score=settings.signal_min_quality,
            )
            if settings.signal_daily_cap > 0
            else None
        )
        self._topic_budgets: dict[str, PriorityDailyBudget] = {}
        self._best_signal_router = best_signal_router or BestSignalRouter(
            daily_cap=settings.best_signals_daily_cap,
            min_score=settings.best_signals_min_score,
            performance_by_family=self._load_best_signal_performance(settings),
            min_confluence_sources=settings.best_signals_min_confluence_sources,
            confluence_window_minutes=settings.best_signals_confluence_window_minutes,
            min_confluence_component_score=settings.best_signals_min_confluence_component_score,
        )
        self._risk_cache: dict[tuple[Chain, str], RiskReport] = {}
        self._pending_best_rechecks: dict[str, tuple[LiveSignal, int]] = {}
        self._sent_keys = (
            self.signal_journal.recent_dedupe_keys()
            if self.signal_journal is not None
            else set()
        )
        self.stats.hydrated_dedupe_keys = len(self._sent_keys)
        self._sent_wallet_signal_keys: set[str] = set()
        self._sent_day: str | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def can_send(self) -> bool:
        return self.sender is not None and bool(self.settings.telegram_topic_ids)

    async def start(self) -> None:
        if not self.settings.signal_worker_enabled or self._task is not None:
            return
        self.stats.running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self.stats.running = False
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run_once(self) -> list[LiveSignal]:
        self.stats.last_run_at = datetime.now(timezone.utc)
        self._reset_daily_counter_if_needed(self.stats.last_run_at)
        if self._global_daily_cap_reached(self.stats.last_run_at):
            await self._recheck_pending_best_signals()
            await self._flush_best_signals()
            return []

        profiles = await self.provider.latest_profiles()
        self.stats.profiles_seen += len(profiles)

        best_by_topic: dict[str, LiveSignal] = {}
        seen_pairs: set[tuple[Chain, str]] = set()
        for pair in await self._latest_direct_pairs():
            if pair.chain not in self._CHAIN_MAX_MC:
                continue
            seen_pairs.add((pair.chain, pair.token_address.lower()))
            self._collect_best_signals(pair, best_by_topic)

        for profile in profiles:
            if profile.chain not in self._CHAIN_MAX_MC:
                continue
            try:
                pair = await self.provider.best_pair(profile)
            except Exception as exc:
                self.stats.pair_lookup_failures += 1
                logger.warning(
                    "Dex pair lookup failed for %s (%s)",
                    profile.address,
                    type(exc).__name__,
                )
                continue
            if not pair:
                continue
            pair_key = (pair.chain, pair.token_address.lower())
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            self._collect_best_signals(pair, best_by_topic)

        sent: list[LiveSignal] = []
        for signal in self._ordered_signals(best_by_topic.values()):
            if len(sent) >= self.settings.signal_max_alerts_per_cycle:
                break
            if self._global_daily_cap_reached(self.stats.last_run_at):
                break
            checked_signal = await self._risk_checked_signal(signal)
            if not checked_signal:
                continue
            if not self.sender:
                continue
            topic_budget = self._topic_budget_for(checked_signal.topic_env_key)
            topic_decision = topic_budget.reserve(checked_signal.quality_score, now=self.stats.last_run_at)
            if not topic_decision.allowed:
                self.stats.rejected_daily_budget += 1
                _increment(self.stats.rejected_budget_by_topic, checked_signal.topic_env_key)
                continue
            global_decision = None
            if self._daily_budget is not None:
                global_decision = self._daily_budget.reserve(checked_signal.quality_score, now=self.stats.last_run_at)
                if not global_decision.allowed:
                    topic_budget.release(checked_signal.quality_score, now=self.stats.last_run_at)
                    self.stats.rejected_daily_budget += 1
                    _increment(self.stats.rejected_budget_by_topic, checked_signal.topic_env_key)
                    continue
            topic_id = (self.settings.telegram_topic_ids or {}).get(checked_signal.topic_env_key, 0)
            if await self._send_to_topic(
                checked_signal.topic_env_key,
                topic_id,
                self._format_signal(checked_signal),
            ):
                self._sent_keys.add(checked_signal.dedupe_key)
                self.stats.alerts_sent += 1
                self.stats.daily_sent = self._daily_sent_count(now=self.stats.last_run_at)
                _increment(self.stats.alerts_by_topic, checked_signal.topic_env_key)
                _increment(self.stats.alerts_by_quality_band, (global_decision or topic_decision).band)
                self._record_signal_journal(checked_signal)
                self._queue_best_signal(checked_signal)
                await self._queue_best_wallet_signals(checked_signal)
                self._remember(checked_signal)
                sent.append(checked_signal)
            else:
                topic_budget.release(checked_signal.quality_score, now=self.stats.last_run_at)
                if self._daily_budget is not None:
                    self._daily_budget.release(checked_signal.quality_score, now=self.stats.last_run_at)

        await self._recheck_pending_best_signals()
        await self._flush_best_signals()
        self.stats.last_error = None
        return sent

    async def _latest_direct_pairs(self) -> list[DexPair]:
        latest_pairs = getattr(self.provider, "latest_pairs", None)
        if not callable(latest_pairs):
            return []
        return await latest_pairs()

    def _collect_best_signals(self, pair: DexPair, best_by_topic: dict[str, LiveSignal]) -> None:
        for signal in self._signals_from_pair(pair):
            self.stats.candidates_seen += 1
            if signal.dedupe_key in self._sent_keys:
                self.stats.deduped += 1
                continue
            topic_id = (self.settings.telegram_topic_ids or {}).get(signal.topic_env_key, 0)
            if topic_id <= 0:
                _increment(self.stats.skipped_unconfigured_by_topic, signal.topic_env_key)
                continue
            _increment(self.stats.candidates_by_topic, signal.topic_env_key)
            previous = best_by_topic.get(signal.topic_env_key)
            if previous is None or signal.quality_score > previous.quality_score:
                best_by_topic[signal.topic_env_key] = signal

    async def _send_to_topic(self, topic_env_key: str, topic_id: int, text: str) -> bool:
        sender = self.sender
        if sender is None:
            return False

        try:
            delivered = await sender.send(topic_id, text)
        except Exception as exc:
            self._record_delivery_failure(topic_env_key)
            logger.warning(
                "Telegram delivery failed for %s (%s)",
                topic_env_key,
                type(exc).__name__,
            )
            return False

        if not delivered:
            self._record_delivery_failure(topic_env_key)
            logger.warning("Telegram delivery returned no confirmation for %s", topic_env_key)
        return delivered

    def _record_delivery_failure(self, topic_env_key: str) -> None:
        self.stats.delivery_failures += 1
        _increment(self.stats.delivery_failures_by_topic, topic_env_key)

    async def _risk_checked_signal(self, signal: LiveSignal) -> LiveSignal | None:
        key = (signal.chain, signal.token_address.lower())
        report = self._risk_cache.get(key)
        if report is None:
            try:
                report = await self.risk_provider.fetch_risk(signal.chain, signal.token_address)
            except Exception as exc:
                self.stats.risk_lookup_failures += 1
                logger.warning(
                    "Risk lookup failed for %s (%s)",
                    signal.token_address,
                    type(exc).__name__,
                )
                return None
            self._risk_cache[key] = report
            self.stats.risk_checked += 1

        if not _risk_report_allows_alert(report, signal):
            self.stats.rejected_risk += 1
            reason = _risk_rejection_reason(report)
            _increment(self.stats.rejected_risk_by_topic, signal.topic_env_key)
            _increment(
                self.stats.rejected_risk_by_topic_reason,
                f"{signal.topic_env_key}:{reason}",
            )
            self._remember_risk_rejection(signal, report, reason)
            return None

        return replace(
            signal,
            risk_level=report.level,
            buy_tax_bps=report.buy_tax_bps,
            sell_tax_bps=report.sell_tax_bps,
            risk_reasons=tuple(report.reasons),
        )

    def _remember_risk_rejection(self, signal: LiveSignal, report: RiskReport, reason: str) -> None:
        self.stats.last_risk_rejections.append(
            {
                "chain": signal.chain.value,
                "topic_env_key": signal.topic_env_key,
                "symbol": signal.symbol,
                "address": signal.token_address,
                "reason": reason,
                "risk_level": report.level.value,
                "risk_reasons": list(report.reasons),
            }
        )
        self.stats.last_risk_rejections = self.stats.last_risk_rejections[-10:]
    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self.can_send:
                    await self.run_once()
            except Exception as exc:
                self.stats.last_error = type(exc).__name__
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.signal_poll_seconds,
                )
            except asyncio.TimeoutError:
                continue

    def _signal_from_pair(self, pair: DexPair) -> LiveSignal | None:
        signals = self._signals_from_pair(pair)
        return signals[0] if signals else None

    def _signals_from_pair(self, pair: DexPair) -> list[LiveSignal]:
        market_cap = pair.market_cap_usd
        liquidity = pair.liquidity_usd
        if market_cap is None or liquidity is None:
            self._reject_low_quality(pair, "missing_market_or_liquidity")
            return []
        if liquidity < 20_000:
            self._reject_low_quality(pair, "liquidity_too_low")
            return []
        if _rug_like_market(pair):
            self._reject_low_quality(pair, "rug_like_market")
            return []
        if market_cap < 25_000 or market_cap > self._CHAIN_MAX_MC[pair.chain]:
            self._reject_low_quality(pair, "market_cap_out_of_range")
            return []
        if (pair.volume_24h_usd or 0) < 25_000:
            self._reject_low_quality(pair, "volume_too_low")
            return []
        if pair.buys_1h < 20 and pair.buys_24h < 75:
            self._reject_low_quality(pair, "buy_pressure_too_low")
            return []

        age_minutes = self._age_minutes(pair)
        quality_score, quality_reasons = self._quality_score(pair, age_minutes)
        min_quality = max(
            self.settings.signal_min_quality,
            90 if pair.chain is Chain.ROBINHOOD else self.settings.signal_min_quality,
        )
        if quality_score < min_quality:
            self._reject_low_quality(pair, "quality_score_below_min")
            return []

        if pair.chain is Chain.ROBINHOOD:
            feature_reasons = self._robinhood_feature_reasons(
                pair,
                age_minutes=age_minutes,
                quality_reasons=quality_reasons,
            )
            if not feature_reasons:
                return []
        else:
            feature_reasons: list[tuple[TopicFeature, list[str]]] = [
                (TopicFeature.FRESHIES, ["latest profile", *quality_reasons])
            ]
            if market_cap <= 500_000:
                feature_reasons.append(
                    (TopicFeature.LOW_MC_FRESHIES, ["latest profile", *quality_reasons, "low market cap"])
                )
            if pair.chain in {Chain.ETHEREUM, Chain.BSC} and (
                quality_score >= 80 or pair.buys_1h >= 100 or pair.buys_5m >= 20
            ):
                feature_reasons.append(
                    (TopicFeature.BIG_FRESHIES, ["latest profile", *quality_reasons, "high quality activity"])
                )
            if pair.chain is Chain.BASE and age_minutes is not None and age_minutes <= 12 * 60:
                feature_reasons.append(
                    (
                        TopicFeature.DEPLOYS,
                        ["latest profile", *quality_reasons, "fresh Base deploy"],
                    )
                )
        return [
            LiveSignal(
                chain=pair.chain,
                feature=feature,
                topic_env_key=topic_env_key(pair.chain, feature),
                token_address=pair.token_address,
                symbol=pair.symbol,
                name=pair.name,
                price_usd=pair.price_usd,
                market_cap_usd=market_cap,
                liquidity_usd=liquidity,
                volume_24h_usd=pair.volume_24h_usd,
                buys_5m=pair.buys_5m,
                buys_1h=pair.buys_1h,
                buys_24h=pair.buys_24h,
                sells_5m=pair.sells_5m,
                sells_1h=pair.sells_1h,
                sells_24h=pair.sells_24h,
                pair_age_minutes=age_minutes,
                price_change_5m=pair.price_change_5m,
                price_change_1h=pair.price_change_1h,
                price_change_24h=pair.price_change_24h,
                url=pair.url,
                reasons=tuple(reasons),
                quality_score=quality_score,
            )
            for feature, reasons in feature_reasons
        ]

    def _robinhood_feature_reasons(
        self,
        pair: DexPair,
        *,
        age_minutes: int | None,
        quality_reasons: list[str],
    ) -> list[tuple[TopicFeature, list[str]]]:
        """Assign exactly one RH topic so each feed represents a distinct setup."""

        if age_minutes is None or age_minutes > 24 * 60:
            self._reject_low_quality(pair, "robinhood_pair_not_fresh")
            return []

        base_reasons = ["latest profile", *quality_reasons]
        market_cap = pair.market_cap_usd or 0
        if market_cap <= 500_000:
            return [
                (
                    TopicFeature.LOW_MC_FRESHIES,
                    [*base_reasons, "Robinhood low-cap freshie"],
                )
            ]
        if self._has_robinhood_big_flow(pair):
            return [
                (
                    TopicFeature.BIG_FRESHIES,
                    [*base_reasons, "large liquid Robinhood buy flow"],
                )
            ]
        if age_minutes <= 4 * 60:
            return [
                (
                    TopicFeature.DEPLOYS,
                    [*base_reasons, "fresh Robinhood deployment"],
                )
            ]
        return [
            (
                TopicFeature.FRESHIES,
                [*base_reasons, "standard Robinhood freshie"],
            )
        ]

    @staticmethod
    def _has_robinhood_big_flow(pair: DexPair) -> bool:
        liquidity = pair.liquidity_usd or 0
        volume = pair.volume_24h_usd or 0
        if liquidity < 200_000 or volume < max(1_000_000, liquidity * 4):
            return False
        if pair.buys_5m < 75 or pair.buys_1h < 1_000:
            return False
        if pair.sells_5m > pair.buys_5m * 0.65:
            return False
        return pair.sells_1h <= pair.buys_1h * 0.55
    def _reject_low_quality(self, pair: DexPair, reason: str) -> None:
        self.stats.rejected_low_quality += 1
        _increment(self.stats.rejected_low_quality_by_reason, reason)
        self.stats.last_low_quality_rejections.append(
            {
                "chain": pair.chain.value,
                "symbol": pair.symbol,
                "address": pair.token_address,
                "reason": reason,
            }
        )
        self.stats.last_low_quality_rejections = self.stats.last_low_quality_rejections[-10:]

    def _ordered_signals(self, signals) -> list[LiveSignal]:
        return sorted(
            signals,
            key=lambda signal: (
                -signal.quality_score,
                _CHAIN_ORDER.get(signal.chain, 99),
                _FEATURE_ORDER.get(signal.feature, 99),
                signal.token_address.lower(),
            ),
        )

    def _quality_score(self, pair: DexPair, age_minutes: int | None) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        liquidity = pair.liquidity_usd or 0
        market_cap = pair.market_cap_usd or 0
        volume = pair.volume_24h_usd or 0

        if liquidity >= 100_000:
            score += 25
            reasons.append("deep liquidity")
        elif liquidity >= 50_000:
            score += 22
            reasons.append("strong liquidity")
        elif liquidity >= 20_000:
            score += 16
            reasons.append("usable liquidity")
        else:
            score += 10
            reasons.append("minimum liquidity")

        if 75_000 <= market_cap <= 500_000:
            score += 20
            reasons.append("early but not microcap")
        elif 500_000 < market_cap <= 5_000_000:
            score += 17
            reasons.append("tradable market cap")
        elif 5_000_000 < market_cap <= 25_000_000:
            score += 12
            reasons.append("larger momentum cap")
        else:
            score += 6

        if pair.buys_1h >= 150 or pair.buys_5m >= 25:
            score += 25
            reasons.append("strong buy pressure")
        elif pair.buys_1h >= 60 or pair.buys_5m >= 10:
            score += 20
            reasons.append("active buy pressure")
        elif pair.buys_1h >= 20:
            score += 12
            reasons.append("confirmed buys")

        if pair.buys_5m and pair.sells_5m <= pair.buys_5m * 0.5:
            score += 4
            reasons.append("clean 5m buy flow")
        elif pair.sells_5m > pair.buys_5m:
            score -= 12

        if pair.buys_1h and pair.sells_1h <= pair.buys_1h * 0.65:
            score += 4
            reasons.append("clean 1h buy flow")
        elif pair.sells_1h >= pair.buys_1h:
            score -= 15
        elif pair.sells_1h >= pair.buys_1h * 0.8:
            score -= 8

        if volume >= max(liquidity * 2, 150_000):
            score += 15
            reasons.append("high volume versus liquidity")
        elif volume >= max(liquidity, 75_000):
            score += 11
            reasons.append("solid volume")
        elif volume >= 25_000:
            score += 6

        if age_minutes is None:
            score += 4
        elif age_minutes <= 6 * 60:
            score += 15
            reasons.append("fresh pair")
        elif age_minutes <= 24 * 60:
            score += 11
            reasons.append("same-day pair")
        elif age_minutes <= 48 * 60:
            score += 6
        elif pair.buys_1h >= 60 or pair.buys_24h >= 300:
            reasons.append("older pair with current buy pressure")

        if pair.price_change_5m is not None and pair.price_change_5m <= -10:
            score -= 10
        if pair.price_change_1h is not None and pair.price_change_1h <= -18:
            score -= 14
        if pair.price_change_24h is not None and pair.price_change_24h <= -35:
            score -= 18

        if liquidity > 0 and volume / liquidity >= 6:
            score -= 10

        return max(0, min(100, score)), reasons

    def _age_minutes(self, pair: DexPair) -> int | None:
        if pair.pair_created_at is None:
            return None
        age = datetime.now(timezone.utc) - pair.pair_created_at
        return max(0, int(age.total_seconds() // 60))

    def _remember(self, signal: LiveSignal) -> None:
        self.stats.last_signals.append(
            {
                "chain": signal.chain.value,
                "feature": signal.feature.value,
                "symbol": signal.symbol,
                "address": signal.token_address,
                "topic_env_key": signal.topic_env_key,
                "price_usd": signal.price_usd,
                "quality_score": signal.quality_score,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.stats.last_signals = self.stats.last_signals[-10:]

    def _queue_best_signal(self, signal: LiveSignal) -> None:
        self.stats.best_signal_candidates_seen += 1
        if signal.risk_level is not RiskLevel.LOW:
            _increment(self.stats.best_signal_skipped_by_reason, "risk_not_low")
            self._remember_pending_best_recheck(signal)
            return
        if not self._best_signal_router.queue(self._best_candidate_from_signal(signal)):
            _increment(self.stats.best_signal_skipped_by_reason, "router_rejected")
        self._sync_best_signal_router_stats()

    def _remember_pending_best_recheck(self, signal: LiveSignal) -> None:
        if signal.risk_level is not RiskLevel.MEDIUM:
            return
        if signal.quality_score < self.settings.best_signals_min_score:
            return
        if len(self._pending_best_rechecks) >= _MAX_PENDING_BEST_RECHECKS:
            _increment(self.stats.best_signal_skipped_by_reason, "pending_recheck_full")
            return
        key = f"{signal.chain.value}:{signal.token_address.lower()}"
        existing = self._pending_best_rechecks.get(key)
        if existing is None or signal.quality_score > existing[0].quality_score:
            self._pending_best_rechecks[key] = (signal, 0)
            self.stats.pending_best_signal_rechecks = len(self._pending_best_rechecks)

    async def _recheck_pending_best_signals(self) -> None:
        if not self._pending_best_rechecks:
            self.stats.pending_best_signal_rechecks = 0
            return
        for key, (signal, attempts) in list(self._pending_best_rechecks.items())[:_BEST_RECHECKS_PER_RUN]:
            report = await self.risk_provider.fetch_risk(signal.chain, signal.token_address)
            self._risk_cache[(signal.chain, signal.token_address.lower())] = report
            self.stats.risk_checked += 1

            if report.level is RiskLevel.LOW and _risk_report_allows_alert(report, signal):
                clean_signal = replace(
                    signal,
                    risk_level=report.level,
                    buy_tax_bps=report.buy_tax_bps,
                    sell_tax_bps=report.sell_tax_bps,
                    risk_reasons=tuple(report.reasons),
                )
                self._queue_best_signal(clean_signal)
                self._pending_best_rechecks.pop(key, None)
                continue

            if not _risk_report_allows_alert(report, signal):
                _increment(self.stats.best_signal_skipped_by_reason, "recheck_risk_rejected")
                self._pending_best_rechecks.pop(key, None)
                continue

            attempts += 1
            if attempts >= _MAX_BEST_RECHECK_ATTEMPTS:
                _increment(self.stats.best_signal_skipped_by_reason, "recheck_expired")
                self._pending_best_rechecks.pop(key, None)
                continue
            self._pending_best_rechecks[key] = (signal, attempts)
        self.stats.pending_best_signal_rechecks = len(self._pending_best_rechecks)

    def _best_candidate_from_signal(self, signal: LiveSignal) -> BestSignalCandidate:
        return BestSignalCandidate(
            source_label=f"V2 {signal.chain.label} {signal.feature.value.replace('_', ' ').title()}",
            chain=signal.chain.value,
            signal_family="v2_live",
            token_address=signal.token_address,
            symbol=signal.symbol,
            name=signal.name,
            score=signal.quality_score,
            reasons=signal.reasons,
            risk_text=_risk_text(signal),
            price_usd=signal.price_usd,
            market_cap_usd=signal.market_cap_usd,
            liquidity_usd=signal.liquidity_usd,
            volume_24h_usd=signal.volume_24h_usd,
            buys_5m=signal.buys_5m,
            buys_1h=signal.buys_1h,
            sells_5m=signal.sells_5m,
            sells_1h=signal.sells_1h,
            age_minutes=signal.pair_age_minutes,
            price_change_5m=signal.price_change_5m,
            price_change_1h=signal.price_change_1h,
            price_change_24h=signal.price_change_24h,
            url=signal.url,
            provenance="v2_risk_checked",
            confluence_source="market_structure",
        )

    def _record_signal_journal(self, signal: LiveSignal) -> None:
        if not self.signal_journal:
            return
        try:
            self.signal_journal.record(
                signal,
                sent_at=self.stats.last_run_at or datetime.now(timezone.utc),
                risk_text=_risk_text(signal),
            )
        except Exception as exc:
            self.stats.journal_last_error = type(exc).__name__
            return
        self.stats.journal_records_written += 1
        self.stats.journal_last_error = None

    def _record_best_signal_journal(
        self,
        candidate: BestSignalCandidate,
        sent_at: datetime,
    ) -> None:
        if not self.signal_journal:
            return
        try:
            self.signal_journal.record_best(candidate, sent_at=sent_at)
        except Exception as exc:
            self.stats.best_signal_journal_last_error = type(exc).__name__
            return
        self.stats.best_signal_journal_records_written += 1
        self.stats.best_signal_journal_last_error = None

    async def _queue_best_wallet_signals(self, signal: LiveSignal) -> None:
        if not self.wallet_performance_provider:
            return
        self.stats.best_wallet_tokens_checked += 1
        try:
            wallet_candidates = await self.wallet_performance_provider.best_wallets_for_token(
                chain=signal.chain,
                token_address=signal.token_address,
                token_symbol=signal.symbol,
                periods=("week", "month", "year"),
            )
        except Exception as exc:
            self.stats.best_wallet_last_error = type(exc).__name__
            return

        self.stats.best_wallet_last_error = None
        self.stats.best_wallet_candidates_seen += len(wallet_candidates)
        if not wallet_candidates:
            self.stats.best_wallet_provider_empty += 1
        for candidate in wallet_candidates:
            period = candidate.period.lower().strip()
            if period in _BEST_WALLET_TOPIC_ENV_BY_PERIOD:
                _increment(self.stats.best_wallet_candidates_by_period, period)
        for period in ("week", "month", "year"):
            period_candidates = tuple(
                candidate
                for candidate in wallet_candidates
                if candidate.period.lower().strip() == period
            )
            score = score_wallet_token_confluence(period_candidates, period=period)
            self.stats.best_wallet_last_score_by_period[period] = score
            best_candidate = best_signal_from_wallet_token_confluence(
                chain=signal.chain.value,
                token_address=signal.token_address,
                token_symbol=signal.symbol,
                token_name=signal.name,
                period=period,
                wallet_candidates=period_candidates,
                min_score=self.settings.best_wallet_min_score,
                risk_text=_risk_text(signal),
                market_cap_usd=signal.market_cap_usd,
                liquidity_usd=signal.liquidity_usd,
                buys_5m=signal.buys_5m,
                buys_1h=signal.buys_1h,
                age_minutes=signal.pair_age_minutes,
                url=signal.url,
            )
            if not best_candidate:
                _increment(self.stats.best_wallet_rejected_by_period, period)
                reason = wallet_token_confluence_rejection_reason(
                    wallet_candidates=period_candidates,
                    period=period,
                    min_score=self.settings.best_wallet_min_score,
                ) or "unknown"
                _increment(self.stats.best_wallet_rejected_by_reason, f"{period}:{reason}")
                continue
            if await self._send_best_wallet_signal(period, best_candidate):
                self.stats.best_wallet_signals_sent += 1
            if self._best_signal_router.queue(best_candidate):
                self.stats.best_wallet_signals_queued += 1
            self._sync_best_signal_router_stats()

    async def _send_best_wallet_signal(
        self,
        period: str,
        candidate: BestSignalCandidate,
    ) -> bool:
        if not self.sender:
            return False
        topic_ids = self.settings.telegram_topic_ids or {}
        topic_key = _BEST_WALLET_TOPIC_ENV_BY_PERIOD.get(period.lower().strip())
        if not topic_key:
            return False
        topic_id = topic_ids.get(topic_key, 0)
        if topic_id <= 0:
            topic_key = _BEST_WALLET_CONFLUENCE_TOPIC_ENV
            topic_id = topic_ids.get(topic_key, 0)
        if topic_id <= 0:
            return False
        if candidate.dedupe_key in self._sent_wallet_signal_keys:
            return False
        if await self._send_to_topic(
            topic_key,
            topic_id,
            format_best_signal(candidate),
        ):
            self._sent_wallet_signal_keys.add(candidate.dedupe_key)
            return True
        return False

    async def _flush_best_signals(self) -> None:
        best_topic_id = (self.settings.telegram_topic_ids or {}).get("TELEGRAM_BEST_SIGNALS_TOPIC_ID", 0)
        if best_topic_id <= 0 or not self.sender:
            return

        async def send_best(text: str) -> bool:
            return await self._send_to_topic(
                "TELEGRAM_BEST_SIGNALS_TOPIC_ID",
                best_topic_id,
                text,
            )

        self.stats.best_signals_sent += await self._best_signal_router.flush(
            send_best,
            now=self.stats.last_run_at,
            on_sent=self._record_best_signal_journal,
        )
        self._sync_best_signal_router_stats()

    def _sync_best_signal_router_stats(self) -> None:
        self.stats.best_signal_rejected_by_reason = self._best_signal_router.rejected_by_reason
        self.stats.pending_best_confluence = self._best_signal_router.pending_confluence_count

    def _reset_daily_counter_if_needed(self, now: datetime) -> None:
        day = now.date().isoformat()
        if self._sent_day == day:
            self.stats.daily_sent = self._daily_sent_count(now=now)
            return
        self._sent_day = day
        self.stats.daily_sent = self._daily_sent_count(now=now)

    def _topic_budget_for(self, topic_env_key: str) -> PriorityDailyBudget:
        budget = self._topic_budgets.get(topic_env_key)
        if budget is None:
            budget = PriorityDailyBudget(
                daily_cap=self.settings.signal_topic_daily_cap,
                min_score=self.settings.signal_min_quality,
            )
            self._topic_budgets[topic_env_key] = budget
        return budget

    def _global_daily_cap_reached(self, now: datetime) -> bool:
        return self._daily_budget is not None and self._daily_budget.sent_count(now=now) >= self.settings.signal_daily_cap

    def _daily_sent_count(self, now: datetime) -> int:
        if self._daily_budget is not None:
            return self._daily_budget.sent_count(now=now)
        return sum(budget.sent_count(now=now) for budget in self._topic_budgets.values())

    def _format_signal(self, signal: LiveSignal) -> str:
        title = f"V2 {signal.chain.label} {signal.feature.value.replace('_', ' ').title()}"
        lines = [
            f"<b>{html.escape(title)}</b>",
            f"${html.escape(signal.symbol)} {html.escape(signal.name)}",
            f"MC: {_money(signal.market_cap_usd)} | Liq: {_money(signal.liquidity_usd)}",
            f"Buys: {signal.buys_5m}/5m | {signal.buys_1h}/1h | {signal.buys_24h}/24h",
            f"Vol 24h: {_money(signal.volume_24h_usd)} | Age: {_age(signal.pair_age_minutes)}",
            f"Quality: {signal.quality_score}/100",
            f"Risk: {_risk_text(signal)}",
            "Why: " + ", ".join(html.escape(reason) for reason in signal.reasons),
            f"<code>{html.escape(signal.token_address)}</code>",
        ]
        if signal.url:
            lines.append(f'<a href="{html.escape(signal.url, quote=True)}">DexScreener</a>')
        return "\n".join(lines)

    def _sender_from_settings(self, settings: V2Settings) -> TelegramSender | None:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return None
        return BotApiTelegramSender(settings.telegram_bot_token, settings.telegram_chat_id)

    def _wallet_provider_from_settings(self, settings: V2Settings) -> WalletPerformanceProvider | None:
        if not settings.best_wallet_signals_enabled or not settings.command_providers_enabled:
            return None
        if not settings.moralis_api_key:
            return None
        return MoralisTopTradersProvider(settings.moralis_api_key)

    def _load_best_signal_performance(self, settings: V2Settings):
        if not settings.best_signal_performance_path:
            return None
        return load_performance_profiles(settings.best_signal_performance_path)


def _money(value: float | None) -> str:
    if value is None:
        return "?"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}k"
    return f"${value:.0f}"


def _age(minutes: int | None) -> str:
    if minutes is None:
        return "?"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _risk_text(signal: LiveSignal) -> str:
    level = signal.risk_level.value if signal.risk_level else "unknown"
    buy_tax = _tax(signal.buy_tax_bps)
    sell_tax = _tax(signal.sell_tax_bps)
    reason = signal.risk_reasons[0] if signal.risk_reasons else "passed"
    return f"{level} | Tax B/S: {buy_tax}/{sell_tax} | {html.escape(reason)}"


def _tax(value: int | None) -> str:
    if value is None:
        return "?"
    return f"{value / 100:.1f}%"


def _risk_rejection_reason(report: RiskReport) -> str:
    if report.is_honeypot or report.delayed_honeypot:
        return "honeypot"
    if report.malicious_contract:
        return "malicious_contract"
    if report.liquidity_pull_risk:
        return "liquidity_pull_risk"
    if max(report.buy_tax_bps or 0, report.sell_tax_bps or 0) >= 500:
        return "high_tax"
    if report.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return f"{report.level.value}_risk"

    joined = " ".join(reason.lower() for reason in report.reasons)
    if any(marker in joined for marker in ("rate limited", "unavailable", "no risk provider", "unexpected payload")):
        return "provider_unavailable"
    if not _risk_reasons_are_actionable(report):
        return "non_actionable_risk"
    return "unknown"

def _risk_report_allows_alert(report: RiskReport, signal: LiveSignal | None = None) -> bool:
    if report.is_honeypot or report.delayed_honeypot:
        return False
    if report.malicious_contract:
        return False
    if report.liquidity_pull_risk:
        return False
    if max(report.buy_tax_bps or 0, report.sell_tax_bps or 0) >= 500:
        return False
    if report.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return False
    if _provider_gap_allows_source_alert(report, signal):
        return True
    return _risk_reasons_are_actionable(report)


def _provider_gap_allows_source_alert(report: RiskReport, signal: LiveSignal | None = None) -> bool:
    if signal is None or signal.quality_score < 90:
        return False
    if report.level is not RiskLevel.MEDIUM:
        return False
    if max(report.buy_tax_bps or 0, report.sell_tax_bps or 0) > 0:
        return False
    joined = " ".join(reason.lower() for reason in report.reasons)
    if "rate limited" in joined or "unexpected payload" in joined:
        return False
    if (
        signal.chain is Chain.ROBINHOOD
        and "independent security indexers unavailable" in joined
    ):
        return (
            signal.quality_score >= 90
            and (signal.liquidity_usd or 0) >= 100_000
            and (signal.volume_24h_usd or 0) >= max(200_000, (signal.liquidity_usd or 0) * 1.5)
            and signal.buys_1h >= 100
            and signal.sells_1h <= signal.buys_1h * 0.5
            and signal.sells_5m <= signal.buys_5m * 0.5
        )
    if "holder data missing or zero holders reported" not in joined:
        return False
    provider_gap = any(
        marker in joined
        for marker in (
            "404 not found",
            "returned no token result",
            "returned no matching token result",
        )
    )
    return provider_gap

def _rug_like_market(pair: DexPair) -> bool:
    price_changes = [
        value
        for value in (pair.price_change_5m, pair.price_change_1h, pair.price_change_24h)
        if value is not None
    ]
    if any(change <= -45 for change in price_changes):
        return True

    if pair.price_change_5m is not None and pair.price_change_5m <= -20 and pair.sells_5m > pair.buys_5m:
        return True

    if pair.sells_1h >= max(20, int(pair.buys_1h * 1.25)):
        return True

    liquidity = pair.liquidity_usd or 0
    volume = pair.volume_24h_usd or 0
    age_minutes = None
    if pair.pair_created_at is not None:
        age_minutes = max(0, int((datetime.now(timezone.utc) - pair.pair_created_at).total_seconds() // 60))
    if liquidity > 0 and volume / liquidity >= 8 and (age_minutes is None or age_minutes <= 90):
        return True

    return False


def _risk_reasons_are_actionable(report: RiskReport) -> bool:
    if report.level is RiskLevel.LOW:
        return True

    joined = " ".join(reason.lower() for reason in report.reasons)
    if not joined:
        return False
    if any(marker in joined for marker in ("rate limited", "unavailable", "no risk provider", "unexpected payload")):
        return False
    non_blocking_markers = (
        "holder data missing or zero holders reported",
        "simulation passed",
        "found no high-risk",
    )
    if report.reasons and all(
        any(marker in reason.lower() for marker in non_blocking_markers)
        for reason in report.reasons
    ):
        return True
    return any(marker in joined for marker in ("simulation passed", "no high-risk", "found no high-risk"))


_CHAIN_ORDER = {
    Chain.ETHEREUM: 0,
    Chain.BASE: 1,
    Chain.BSC: 2,
    Chain.ROBINHOOD: 3,
}

_FEATURE_ORDER = {
    TopicFeature.DEPLOYS: 0,
    TopicFeature.BIG_FRESHIES: 0,
    TopicFeature.LOW_MC_FRESHIES: 1,
    TopicFeature.FRESHIES: 2,
}


def _increment(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1
