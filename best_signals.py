"""Shared best-signal routing for the one high-conviction Telegram feed."""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from quality_budget import PriorityDailyBudget, score_v1_alert_message


SendBestSignal = Callable[[str], Awaitable[bool]]

_ADDRESS_RE = re.compile(r"\b(0x[a-fA-F0-9]{32,}|[1-9A-HJ-NP-Za-km-z]{32,})\b")
_CODE_RE = re.compile(r"<code>([^<]+)</code>", re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\$([^\s<|]+)")
_REPORTED_SCORE_RE = re.compile(
    r"\b(?:strength|score|quality)\s*:\s*(\d{1,3})\s*/\s*100\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BestSignalCandidate:
    source_label: str
    chain: str
    signal_family: str
    token_address: str
    symbol: str
    name: str
    score: int
    reasons: tuple[str, ...]
    risk_text: str | None = None
    market_cap_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    buys_5m: int | None = None
    buys_1h: int | None = None
    sells_5m: int | None = None
    sells_1h: int | None = None
    age_minutes: int | None = None
    price_change_5m: float | None = None
    price_change_1h: float | None = None
    price_change_24h: float | None = None
    backtest_text: str | None = None
    url: str | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.chain.lower()}:{self.token_address.lower()}"


@dataclass(frozen=True, slots=True)
class BestSignalPerformance:
    sample_size: int
    hit_2x_rate: float
    rug_rate: float
    median_max_multiple: float
    average_max_multiple: float

    def summary_text(self) -> str:
        return (
            f"Replay: {self.hit_2x_rate:.0%} hit 2x, "
            f"{self.rug_rate:.0%} rug rate, "
            f"{self.median_max_multiple:.2g}x median max "
            f"({self.sample_size} samples)"
        )


class BestSignalRouter:
    """Buffers elite candidates and emits the best few, not the first few."""

    def __init__(
        self,
        daily_cap: int = 0,
        min_score: int = 98,
        dedupe_hours: int = 24,
        chain_daily_caps: dict[str, int] | None = None,
        chain_cooldown_minutes: dict[str, int] | None = None,
        performance_by_family: dict[str, BestSignalPerformance] | None = None,
    ):
        if min_score >= 100:
            raise ValueError("min_score must be below 100 so elite routing can reserve priority bands")
        self.daily_cap = daily_cap
        self.min_score = min_score
        self._budget = (
            PriorityDailyBudget(
                daily_cap=daily_cap,
                min_score=min_score,
                high_score=min(99, min_score + 3),
                elite_score=100,
            )
            if daily_cap > 0
            else None
        )
        self._dedupe_ttl = timedelta(hours=dedupe_hours)
        self._chain_daily_caps = _normalize_int_map(chain_daily_caps)
        self._chain_cooldowns = {
            chain: timedelta(minutes=minutes)
            for chain, minutes in _normalize_int_map(chain_cooldown_minutes).items()
        }
        self._buffer: dict[str, BestSignalCandidate] = {}
        self._sent_at_by_key: dict[str, datetime] = {}
        self._sent_count_by_day_and_chain: dict[tuple[str, str], int] = {}
        self._sent_at_by_chain: dict[str, datetime] = {}
        self._rejected_by_reason: dict[str, int] = {}
        self._performance_by_family = {
            key.lower().strip(): value
            for key, value in (performance_by_family or {}).items()
        }

    @property
    def rejected_by_reason(self) -> dict[str, int]:
        return dict(self._rejected_by_reason)

    def queue(self, candidate: BestSignalCandidate, now: datetime | None = None) -> bool:
        now = _normalize_now(now)
        if candidate.score < self.min_score:
            self._record_reject("score_below_min")
            return False
        gate_rejection = _best_gate_rejection_reason(candidate)
        if gate_rejection:
            self._record_reject(gate_rejection)
            return False
        performance_rejection = _performance_rejection_reason(
            self._performance_by_family.get(candidate.signal_family.lower().strip())
        )
        if performance_rejection:
            self._record_reject(performance_rejection)
            return False
        self._expire_dedupe(now)
        if candidate.dedupe_key in self._sent_at_by_key:
            self._record_reject("dedupe")
            return False

        existing = self._buffer.get(candidate.dedupe_key)
        if existing is None or _sort_key(candidate) < _sort_key(existing):
            self._buffer[candidate.dedupe_key] = candidate
        return True

    def _record_reject(self, reason: str) -> None:
        self._rejected_by_reason[reason] = self._rejected_by_reason.get(reason, 0) + 1

    async def flush(self, send: SendBestSignal, now: datetime | None = None) -> int:
        now = _normalize_now(now)
        sent = 0
        for candidate in sorted(self._buffer.values(), key=_sort_key):
            if not self._chain_allows(candidate, now):
                continue
            if self._budget:
                decision = self._budget.reserve(candidate.score, now=now)
                if not decision.allowed:
                    continue
            candidate_to_send = self._candidate_with_performance_summary(candidate)
            if await send(format_best_signal(candidate_to_send)):
                self._sent_at_by_key[candidate.dedupe_key] = now
                self._record_chain_sent(candidate, now)
                self._buffer.pop(candidate.dedupe_key, None)
                sent += 1
            else:
                if self._budget:
                    self._budget.release(candidate.score, now=now)
        return sent

    def _expire_dedupe(self, now: datetime) -> None:
        expired = [
            key
            for key, sent_at in self._sent_at_by_key.items()
            if now - sent_at >= self._dedupe_ttl
        ]
        for key in expired:
            self._sent_at_by_key.pop(key, None)

    def _chain_allows(self, candidate: BestSignalCandidate, now: datetime) -> bool:
        chain = candidate.chain.lower()
        daily_cap = self._chain_daily_caps.get(chain)
        if daily_cap is not None:
            chain_key = (_day_key(now), chain)
            if self._sent_count_by_day_and_chain.get(chain_key, 0) >= daily_cap:
                return False

        cooldown = self._chain_cooldowns.get(chain)
        if cooldown is not None:
            sent_at = self._sent_at_by_chain.get(chain)
            if sent_at and now - sent_at < cooldown:
                return False
        return True

    def _record_chain_sent(self, candidate: BestSignalCandidate, now: datetime) -> None:
        chain = candidate.chain.lower()
        chain_key = (_day_key(now), chain)
        self._sent_count_by_day_and_chain[chain_key] = self._sent_count_by_day_and_chain.get(chain_key, 0) + 1
        self._sent_at_by_chain[chain] = now

    def _candidate_with_performance_summary(self, candidate: BestSignalCandidate) -> BestSignalCandidate:
        if candidate.backtest_text:
            return candidate
        profile = self._performance_by_family.get(candidate.signal_family.lower().strip())
        if profile is None:
            return candidate
        return replace(candidate, backtest_text=profile.summary_text())


def candidate_from_v1_message(message: str, source_label: str = "V1 SOL") -> BestSignalCandidate | None:
    address = _extract_address(message)
    if not address:
        return None
    score = _score_v1_for_best_feed(message)
    symbol = _extract_symbol(message)
    family = _family_from_message(message)
    return BestSignalCandidate(
        source_label=f"{source_label} {family.replace('_', ' ').title()}",
        chain="solana",
        signal_family=family,
        token_address=address,
        symbol=symbol,
        name=symbol,
        score=score,
        reasons=(_short_reason(message),),
        risk_text="V1 signal; use links for manual risk check",
        url=_extract_url(message),
    )


def format_best_signal(candidate: BestSignalCandidate) -> str:
    lines = [
        "<b>Best Signal</b>",
        f"{html.escape(candidate.source_label)} | Score: {candidate.score}/100",
        f"${html.escape(candidate.symbol)} {html.escape(candidate.name)}",
    ]
    metrics = _metrics_line(candidate)
    if metrics:
        lines.append(metrics)
    if candidate.risk_text:
        lines.append(f"Risk: {html.escape(candidate.risk_text)}")
    if candidate.backtest_text:
        lines.append(html.escape(candidate.backtest_text))
    if candidate.reasons:
        lines.append("Why: " + ", ".join(html.escape(reason) for reason in candidate.reasons[:4]))
    lines.append(f"<code>{html.escape(candidate.token_address)}</code>")
    if candidate.url:
        lines.append(f'<a href="{html.escape(candidate.url, quote=True)}">Open</a>')
    return "\n".join(lines)


def _sort_key(candidate: BestSignalCandidate) -> tuple:
    return (
        -_effective_best_score(candidate),
        _risk_rank(candidate.risk_text),
        -(candidate.liquidity_usd or 0),
        -(candidate.volume_24h_usd or 0),
        -(candidate.buys_5m or 0),
        -(candidate.buys_1h or 0),
        candidate.sells_5m or 0,
        candidate.sells_1h or 0,
        candidate.age_minutes if candidate.age_minutes is not None else 10**9,
        candidate.token_address.lower(),
    )


def _effective_best_score(candidate: BestSignalCandidate) -> int:
    score = candidate.score
    if candidate.signal_family.lower().startswith("best_wallet_coin_"):
        score += 3
    return min(103, score)


def _risk_rank(risk_text: str | None) -> int:
    text = (risk_text or "").lower()
    if "low" in text or "passed" in text:
        return 0
    if "medium" in text:
        return 1
    if "unknown" in text:
        return 2
    if "high" in text or "critical" in text:
        return 3
    return 2


def _performance_rejection_reason(profile: BestSignalPerformance | None) -> str | None:
    if profile is None:
        return None
    if profile.sample_size < 20:
        return "backtest_sample_too_small"
    if profile.hit_2x_rate < 0.18:
        return "backtest_hit_rate_too_low"
    if profile.rug_rate > 0.15:
        return "backtest_rug_rate_too_high"
    if profile.median_max_multiple < 1.25:
        return "backtest_median_x_too_low"
    return None


def _passes_elite_best_gate(candidate: BestSignalCandidate) -> bool:
    return _best_gate_rejection_reason(candidate) is None


def _best_gate_rejection_reason(candidate: BestSignalCandidate) -> str | None:
    chain = candidate.chain.lower().strip()
    family = candidate.signal_family.lower().strip()

    if chain == "solana":
        return _solana_best_rejection_reason(candidate)

    if not _risk_text_allows_best(candidate.risk_text):
        return "risk_not_clean"

    if family.startswith("best_wallet_coin_"):
        return _evm_metrics_rejection_reason(candidate, allow_older=True)

    return _evm_metrics_rejection_reason(candidate, allow_older=False)


def _solana_candidate_allows_best(candidate: BestSignalCandidate) -> bool:
    return _solana_best_rejection_reason(candidate) is None


def _solana_best_rejection_reason(candidate: BestSignalCandidate) -> str | None:
    family = candidate.signal_family.lower().strip()
    if family in {"freshies", "sol_signal"}:
        return "solana_basic_source_not_best"
    if family == "strongfloor":
        return None if candidate.score >= 98 else "score_below_solana_family_floor"
    if family in {"dormants", "big_dormants", "freshies_wizard", "strong_launch", "streamflow"}:
        return None if candidate.score >= 99 else "score_below_solana_family_floor"
    return None if candidate.score >= 100 else "score_below_solana_family_floor"


def _risk_text_allows_best(risk_text: str | None) -> bool:
    text = (risk_text or "").lower()
    if "low" not in text and "passed" not in text:
        return False
    blocked_markers = (
        "unknown",
        "medium",
        "high",
        "critical",
        "honeypot failed",
        "honeypot detected",
        "delayed honeypot",
        "rate limited",
        "unavailable",
        "no risk provider",
        "unexpected payload",
        "liquidity is not locked",
        "tax b/s: ?",
        "/?",
        "?/",
    )
    return not any(marker in text for marker in blocked_markers)


def _evm_metrics_allow_best(candidate: BestSignalCandidate, *, allow_older: bool) -> bool:
    return _evm_metrics_rejection_reason(candidate, allow_older=allow_older) is None


def _evm_metrics_rejection_reason(candidate: BestSignalCandidate, *, allow_older: bool) -> str | None:
    market_cap = candidate.market_cap_usd or 0
    liquidity = candidate.liquidity_usd or 0
    buys_5m = candidate.buys_5m or 0
    buys_1h = candidate.buys_1h or 0
    sells_5m = candidate.sells_5m or 0
    sells_1h = candidate.sells_1h or 0
    age_minutes = candidate.age_minutes

    if market_cap < 75_000 or market_cap > 25_000_000:
        return "market_cap_out_of_range"

    min_liquidity = {
        "ethereum": 100_000,
        "bsc": 75_000,
        "base": 60_000,
    }.get(candidate.chain.lower().strip(), 75_000)
    if liquidity < min_liquidity:
        return "liquidity_too_low"

    if buys_5m < 20 and buys_1h < 120:
        return "buy_pressure_too_low"

    if sells_5m and buys_5m and sells_5m > buys_5m * 0.75:
        return "sell_pressure_too_high"
    if sells_1h and buys_1h and sells_1h > buys_1h * 0.85:
        return "sell_pressure_too_high"

    if _has_bad_price_action(candidate):
        return "price_action_bad"

    volume = candidate.volume_24h_usd or 0
    if liquidity > 0 and volume / liquidity >= 6:
        if age_minutes is None or age_minutes <= 6 * 60:
            return "volume_liquidity_churn"

    if allow_older:
        return None
    if age_minutes is None:
        return "age_unknown"
    if age_minutes <= 24 * 60 or buys_1h >= 180:
        return None
    return "pair_too_old"


def _has_bad_price_action(candidate: BestSignalCandidate) -> bool:
    if candidate.price_change_5m is not None and candidate.price_change_5m <= -10:
        return True
    if candidate.price_change_1h is not None and candidate.price_change_1h <= -18:
        return True
    if candidate.price_change_24h is not None and candidate.price_change_24h <= -35:
        return True
    return False


def _metrics_line(candidate: BestSignalCandidate) -> str:
    parts = []
    if candidate.market_cap_usd is not None:
        parts.append(f"MC: {_money(candidate.market_cap_usd)}")
    if candidate.liquidity_usd is not None:
        parts.append(f"Liq: {_money(candidate.liquidity_usd)}")
    if candidate.buys_5m is not None or candidate.buys_1h is not None:
        parts.append(f"Buys: {candidate.buys_5m or 0}/5m | {candidate.buys_1h or 0}/1h")
    if candidate.sells_5m is not None or candidate.sells_1h is not None:
        parts.append(f"Sells: {candidate.sells_5m or 0}/5m | {candidate.sells_1h or 0}/1h")
    if candidate.age_minutes is not None:
        parts.append(f"Age: {_age(candidate.age_minutes)}")
    return " | ".join(parts)


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}k"
    return f"${value:.0f}"


def _age(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _extract_address(message: str) -> str | None:
    code_match = _CODE_RE.search(message)
    if code_match:
        return code_match.group(1).strip()
    plain = re.sub(r"<[^>]+>", " ", html.unescape(message))
    match = _ADDRESS_RE.search(plain)
    return match.group(1) if match else None


def _extract_symbol(message: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", message))
    match = _SYMBOL_RE.search(plain)
    return match.group(1) if match else "UNKNOWN"


def _extract_url(message: str) -> str | None:
    urls = _HREF_RE.findall(message)
    for url in urls:
        lowered = url.lower()
        if "dexscreener" in lowered or "axiom" in lowered or "photon" in lowered:
            return url
    return urls[0] if urls else None


def _score_v1_for_best_feed(message: str) -> int:
    score = score_v1_alert_message(message)
    reported_score = _reported_score_from_message(message)
    if reported_score is not None:
        return reported_score
    return min(score, 94)


def _reported_score_from_message(message: str) -> int | None:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", message))
    match = _REPORTED_SCORE_RE.search(plain)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _family_from_message(message: str) -> str:
    lower = message.lower()
    if "strongfloor" in lower or "strong floor" in lower:
        return "strongfloor"
    if "strong launch" in lower:
        return "strong_launch"
    if "streamflow" in lower:
        return "streamflow"
    if "dev held" in lower:
        return "dev_held"
    if "good creator" in lower or "creator" in lower:
        return "good_creator"
    if "socials" in lower:
        return "socials"
    if "sns" in lower:
        return "sns"
    if "vanish" in lower:
        return "vanish"
    if "dormant" in lower:
        return "dormants"
    if "fresh buys" in lower or "wizard" in lower:
        return "freshies_wizard"
    if "freshies" in lower:
        return "freshies"
    if "migration" in lower:
        return "migration"
    if "bundle" in lower:
        return "bundles"
    if "pattern" in lower:
        return "patterns"
    return "sol_signal"


def _short_reason(message: str) -> str:
    for line in html.unescape(re.sub(r"<[^>]+>", " ", message)).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return "elite V1 signal"


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _day_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _normalize_int_map(values: dict[str, int] | None) -> dict[str, int]:
    if not values:
        return {}
    return {
        key.lower().strip(): value
        for key, value in values.items()
        if key.strip() and value > 0
    }
