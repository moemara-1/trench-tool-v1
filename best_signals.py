"""Shared best-signal routing for the one high-conviction Telegram feed."""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from quality_budget import PriorityDailyBudget, score_v1_alert_message


SendBestSignal = Callable[[str], Awaitable[bool]]

_ADDRESS_RE = re.compile(r"\b(0x[a-fA-F0-9]{32,}|[1-9A-HJ-NP-Za-km-z]{32,})\b")
_CODE_RE = re.compile(r"<code>([^<]+)</code>", re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\$([^\s<|]+)")


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
    buys_5m: int | None = None
    buys_1h: int | None = None
    age_minutes: int | None = None
    url: str | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.chain.lower()}:{self.token_address.lower()}:{self.signal_family.lower()}"


class BestSignalRouter:
    """Buffers elite candidates and emits the best few, not the first few."""

    def __init__(
        self,
        daily_cap: int = 0,
        min_score: int = 95,
        dedupe_hours: int = 24,
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
        self._buffer: dict[str, BestSignalCandidate] = {}
        self._sent_at_by_key: dict[str, datetime] = {}

    def queue(self, candidate: BestSignalCandidate, now: datetime | None = None) -> bool:
        now = _normalize_now(now)
        if candidate.score < self.min_score:
            return False
        self._expire_dedupe(now)
        if candidate.dedupe_key in self._sent_at_by_key:
            return False

        existing = self._buffer.get(candidate.dedupe_key)
        if existing is None or _sort_key(candidate) < _sort_key(existing):
            self._buffer[candidate.dedupe_key] = candidate
        return True

    async def flush(self, send: SendBestSignal, now: datetime | None = None) -> int:
        now = _normalize_now(now)
        sent = 0
        for candidate in sorted(self._buffer.values(), key=_sort_key):
            if self._budget:
                decision = self._budget.reserve(candidate.score, now=now)
                if not decision.allowed:
                    continue
            if await send(format_best_signal(candidate)):
                self._sent_at_by_key[candidate.dedupe_key] = now
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


def candidate_from_v1_message(message: str, source_label: str = "V1 SOL") -> BestSignalCandidate | None:
    address = _extract_address(message)
    if not address:
        return None
    score = score_v1_alert_message(message)
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
    if candidate.reasons:
        lines.append("Why: " + ", ".join(html.escape(reason) for reason in candidate.reasons[:4]))
    lines.append(f"<code>{html.escape(candidate.token_address)}</code>")
    if candidate.url:
        lines.append(f'<a href="{html.escape(candidate.url, quote=True)}">Open</a>')
    return "\n".join(lines)


def _sort_key(candidate: BestSignalCandidate) -> tuple:
    return (
        -candidate.score,
        _risk_rank(candidate.risk_text),
        -(candidate.liquidity_usd or 0),
        -(candidate.buys_5m or 0),
        -(candidate.buys_1h or 0),
        candidate.age_minutes if candidate.age_minutes is not None else 10**9,
        candidate.token_address.lower(),
    )


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


def _metrics_line(candidate: BestSignalCandidate) -> str:
    parts = []
    if candidate.market_cap_usd is not None:
        parts.append(f"MC: {_money(candidate.market_cap_usd)}")
    if candidate.liquidity_usd is not None:
        parts.append(f"Liq: {_money(candidate.liquidity_usd)}")
    if candidate.buys_5m is not None or candidate.buys_1h is not None:
        parts.append(f"Buys: {candidate.buys_5m or 0}/5m | {candidate.buys_1h or 0}/1h")
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
