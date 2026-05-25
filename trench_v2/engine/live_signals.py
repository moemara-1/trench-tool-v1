"""Conservative live signal worker for V2 Telegram topics."""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol

from best_signals import BestSignalCandidate, BestSignalRouter
from quality_budget import PriorityDailyBudget
from trench_v2.config import V2Settings
from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.providers.base import RiskProvider
from trench_v2.providers.dexscreener import DexPair, DexScreenerProvider, DexTokenProfile
from trench_v2.providers.factory import build_risk_provider
from trench_v2.providers.wallet_performance import MoralisTopTradersProvider
from trench_v2.telegram.sender import BotApiTelegramSender, TelegramSender
from trench_v2.telegram.topics import TopicFeature, topic_env_key
from wallet_performance import WalletPerformanceCandidate, best_signal_from_wallet_performance


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
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    buys_5m: int
    buys_1h: int
    buys_24h: int
    pair_age_minutes: int | None
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
    candidates_seen: int = 0
    rejected_low_quality: int = 0
    alerts_sent: int = 0
    deduped: int = 0
    daily_sent: int = 0
    rejected_daily_budget: int = 0
    risk_checked: int = 0
    rejected_risk: int = 0
    best_signals_sent: int = 0
    best_wallet_candidates_seen: int = 0
    best_wallet_signals_queued: int = 0
    best_wallet_last_error: str | None = None
    candidates_by_topic: dict[str, int] = field(default_factory=dict)
    alerts_by_topic: dict[str, int] = field(default_factory=dict)
    alerts_by_quality_band: dict[str, int] = field(default_factory=dict)
    last_signals: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "profiles_seen": self.profiles_seen,
            "candidates_seen": self.candidates_seen,
            "rejected_low_quality": self.rejected_low_quality,
            "alerts_sent": self.alerts_sent,
            "deduped": self.deduped,
            "daily_sent": self.daily_sent,
            "rejected_daily_budget": self.rejected_daily_budget,
            "risk_checked": self.risk_checked,
            "rejected_risk": self.rejected_risk,
            "best_signals_sent": self.best_signals_sent,
            "best_wallet_candidates_seen": self.best_wallet_candidates_seen,
            "best_wallet_signals_queued": self.best_wallet_signals_queued,
            "best_wallet_last_error": self.best_wallet_last_error,
            "candidates_by_topic": dict(sorted(self.candidates_by_topic.items())),
            "alerts_by_topic": dict(sorted(self.alerts_by_topic.items())),
            "alerts_by_quality_band": dict(sorted(self.alerts_by_quality_band.items())),
            "last_signals": self.last_signals[-10:],
        }


class LiveSignalWorker:
    """Poll latest token profiles and send low-noise topic alerts."""

    _CHAIN_MAX_MC = {
        Chain.ETHEREUM: 500_000_000,
        Chain.BASE: 25_000_000,
        Chain.BSC: 500_000_000,
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
        self._daily_budget = PriorityDailyBudget(
            daily_cap=settings.signal_daily_cap,
            min_score=settings.signal_min_quality,
        )
        self._best_signal_router = best_signal_router or BestSignalRouter(
            daily_cap=settings.best_signals_daily_cap,
            min_score=settings.best_signals_min_score,
        )
        self._risk_cache: dict[tuple[Chain, str], RiskReport] = {}
        self._sent_keys: set[str] = set()
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
        if self._daily_budget.sent_count(now=self.stats.last_run_at) >= self.settings.signal_daily_cap:
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
            pair = await self.provider.best_pair(profile)
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
            if self._daily_budget.sent_count(now=self.stats.last_run_at) >= self.settings.signal_daily_cap:
                break
            checked_signal = await self._risk_checked_signal(signal)
            if not checked_signal:
                continue
            if not self.sender:
                continue
            decision = self._daily_budget.reserve(checked_signal.quality_score, now=self.stats.last_run_at)
            if not decision.allowed:
                self.stats.rejected_daily_budget += 1
                continue
            topic_id = (self.settings.telegram_topic_ids or {}).get(checked_signal.topic_env_key, 0)
            if await self.sender.send(topic_id, self._format_signal(checked_signal)):
                self._sent_keys.add(checked_signal.dedupe_key)
                self.stats.alerts_sent += 1
                self.stats.daily_sent = self._daily_budget.sent_count(now=self.stats.last_run_at)
                _increment(self.stats.alerts_by_topic, checked_signal.topic_env_key)
                _increment(self.stats.alerts_by_quality_band, decision.band)
                self._queue_best_signal(checked_signal)
                await self._queue_best_wallet_signals(checked_signal)
                self._remember(checked_signal)
                sent.append(checked_signal)
            else:
                self._daily_budget.release(checked_signal.quality_score, now=self.stats.last_run_at)

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
            _increment(self.stats.candidates_by_topic, signal.topic_env_key)
            if signal.dedupe_key in self._sent_keys:
                self.stats.deduped += 1
                continue
            topic_id = (self.settings.telegram_topic_ids or {}).get(signal.topic_env_key, 0)
            if topic_id <= 0:
                continue
            previous = best_by_topic.get(signal.topic_env_key)
            if previous is None or signal.quality_score > previous.quality_score:
                best_by_topic[signal.topic_env_key] = signal

    async def _risk_checked_signal(self, signal: LiveSignal) -> LiveSignal | None:
        key = (signal.chain, signal.token_address.lower())
        report = self._risk_cache.get(key)
        if report is None:
            report = await self.risk_provider.fetch_risk(signal.chain, signal.token_address)
            self._risk_cache[key] = report
            self.stats.risk_checked += 1

        if not _risk_report_allows_alert(report):
            self.stats.rejected_risk += 1
            return None

        return replace(
            signal,
            risk_level=report.level,
            buy_tax_bps=report.buy_tax_bps,
            sell_tax_bps=report.sell_tax_bps,
            risk_reasons=tuple(report.reasons),
        )

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
            return []
        if liquidity < 10_000:
            self.stats.rejected_low_quality += 1
            return []
        if market_cap < 25_000 or market_cap > self._CHAIN_MAX_MC[pair.chain]:
            self.stats.rejected_low_quality += 1
            return []
        if (pair.volume_24h_usd or 0) < 25_000:
            self.stats.rejected_low_quality += 1
            return []
        if pair.buys_1h < 20 and pair.buys_24h < 75:
            self.stats.rejected_low_quality += 1
            return []

        age_minutes = self._age_minutes(pair)
        quality_score, quality_reasons = self._quality_score(pair, age_minutes)
        if quality_score < self.settings.signal_min_quality:
            self.stats.rejected_low_quality += 1
            return []

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
                (TopicFeature.DEPLOYS, ["latest profile", *quality_reasons, "fresh Base deploy"])
            )

        return [
            LiveSignal(
                chain=pair.chain,
                feature=feature,
                topic_env_key=topic_env_key(pair.chain, feature),
                token_address=pair.token_address,
                symbol=pair.symbol,
                name=pair.name,
                market_cap_usd=market_cap,
                liquidity_usd=liquidity,
                volume_24h_usd=pair.volume_24h_usd,
                buys_5m=pair.buys_5m,
                buys_1h=pair.buys_1h,
                buys_24h=pair.buys_24h,
                pair_age_minutes=age_minutes,
                url=pair.url,
                reasons=tuple(reasons),
                quality_score=quality_score,
            )
            for feature, reasons in feature_reasons
        ]

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

        return min(100, score), reasons

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
                "quality_score": signal.quality_score,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.stats.last_signals = self.stats.last_signals[-10:]

    def _queue_best_signal(self, signal: LiveSignal) -> None:
        self._best_signal_router.queue(
            BestSignalCandidate(
                source_label=f"V2 {signal.chain.label} {signal.feature.value.replace('_', ' ').title()}",
                chain=signal.chain.value,
                signal_family="v2_live",
                token_address=signal.token_address,
                symbol=signal.symbol,
                name=signal.name,
                score=signal.quality_score,
                reasons=signal.reasons,
                risk_text=_risk_text(signal),
                market_cap_usd=signal.market_cap_usd,
                liquidity_usd=signal.liquidity_usd,
                buys_5m=signal.buys_5m,
                buys_1h=signal.buys_1h,
                age_minutes=signal.pair_age_minutes,
                url=signal.url,
            )
        )

    async def _queue_best_wallet_signals(self, signal: LiveSignal) -> None:
        if not self.wallet_performance_provider:
            return
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

        self.stats.best_wallet_candidates_seen += len(wallet_candidates)
        for wallet_candidate in wallet_candidates:
            best_candidate = best_signal_from_wallet_performance(
                wallet_candidate,
                min_score=self.settings.best_wallet_min_score,
            )
            if best_candidate and self._best_signal_router.queue(best_candidate):
                self.stats.best_wallet_signals_queued += 1

    async def _flush_best_signals(self) -> None:
        best_topic_id = (self.settings.telegram_topic_ids or {}).get("TELEGRAM_BEST_SIGNALS_TOPIC_ID", 0)
        if best_topic_id <= 0 or not self.sender:
            return

        async def send_best(text: str) -> bool:
            return await self.sender.send(best_topic_id, text)

        self.stats.best_signals_sent += await self._best_signal_router.flush(
            send_best,
            now=self.stats.last_run_at,
        )

    def _reset_daily_counter_if_needed(self, now: datetime) -> None:
        day = now.date().isoformat()
        if self._sent_day == day:
            self.stats.daily_sent = self._daily_budget.sent_count(now=now)
            return
        self._sent_day = day
        self.stats.daily_sent = self._daily_budget.sent_count(now=now)

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


def _risk_report_allows_alert(report: RiskReport) -> bool:
    if report.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return False
    if report.is_honeypot or report.delayed_honeypot:
        return False
    if report.malicious_contract or report.liquidity_pull_risk:
        return False
    if max(report.buy_tax_bps or 0, report.sell_tax_bps or 0) >= 500:
        return False
    return _risk_reasons_are_actionable(report)


def _risk_reasons_are_actionable(report: RiskReport) -> bool:
    if report.level is RiskLevel.LOW:
        return True

    joined = " ".join(reason.lower() for reason in report.reasons)
    if not joined:
        return False
    if any(marker in joined for marker in ("rate limited", "unavailable", "no risk provider", "unexpected payload")):
        return False
    return any(marker in joined for marker in ("simulation passed", "no high-risk", "found no high-risk"))


_CHAIN_ORDER = {
    Chain.ETHEREUM: 0,
    Chain.BASE: 1,
    Chain.BSC: 2,
}

_FEATURE_ORDER = {
    TopicFeature.DEPLOYS: 0,
    TopicFeature.BIG_FRESHIES: 0,
    TopicFeature.LOW_MC_FRESHIES: 1,
    TopicFeature.FRESHIES: 2,
}


def _increment(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1
