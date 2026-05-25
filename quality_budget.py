"""Priority-aware daily alert budgets shared by V1 and V2."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone


STANDARD_BAND = "standard"
HIGH_BAND = "high"
ELITE_BAND = "elite"

_MONEY_RE = re.compile(r"\b(?:mc:\s*)?\$?\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\b")
_MC_RE = re.compile(r"\bMC:\s*\$?\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\b", re.IGNORECASE)
_SOL_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*SOL\b", re.IGNORECASE)
_AGE_RE = re.compile(r"\bCA:\s*(\d+)\s*([mhd])\b", re.IGNORECASE)
_LAST_SEEN_RE = re.compile(r"\bLS:\s*(\d+)\s*d\b", re.IGNORECASE)
_FRESH_BUYS_RE = re.compile(r"\b(\d+)\s+fresh\s+buys?\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PriorityBudgetDecision:
    allowed: bool
    reason: str
    band: str


class PriorityDailyBudget:
    """Daily cap that preserves slots for better alerts.

    A plain daily cap lets the first acceptable alerts spend the whole day.
    This budget caps lower quality bands separately, so weaker signals cannot
    consume the slots intended for stronger signals later in the day.
    """

    def __init__(
        self,
        daily_cap: int = 30,
        min_score: int = 0,
        standard_daily_cap: int | None = None,
        high_daily_cap: int | None = None,
        high_score: int = 90,
        elite_score: int = 95,
    ):
        if daily_cap < 1:
            raise ValueError("daily_cap must be positive")
        if min_score < 0 or min_score > 100:
            raise ValueError("min_score must be between 0 and 100")
        if high_score <= min_score or high_score > 100:
            raise ValueError("high_score must be greater than min_score and at most 100")
        if elite_score <= high_score or elite_score > 100:
            raise ValueError("elite_score must be greater than high_score and at most 100")

        self.daily_cap = daily_cap
        self.min_score = min_score
        self.high_score = high_score
        self.elite_score = elite_score
        self.standard_daily_cap = _bounded_cap(
            standard_daily_cap,
            default=max(1, daily_cap // 4),
            daily_cap=daily_cap,
        )
        self.high_daily_cap = _bounded_cap(
            high_daily_cap,
            default=max(1, daily_cap // 2),
            daily_cap=daily_cap,
        )
        self._sent_count_by_day: dict[str, int] = {}
        self._sent_count_by_day_and_band: dict[tuple[str, str], int] = {}

    def should_send(self, score: int, now: datetime | None = None) -> PriorityBudgetDecision:
        now = _normalize_now(now)
        band = self.band_for_score(score)
        day_key = _day_key(now)

        if score < self.min_score:
            return PriorityBudgetDecision(False, "blocked by quality floor", band)

        if self._sent_count_by_day.get(day_key, 0) >= self.daily_cap:
            return PriorityBudgetDecision(False, "blocked by daily cap", band)

        if band == STANDARD_BAND and self.sent_count(band=STANDARD_BAND, now=now) >= self.standard_daily_cap:
            return PriorityBudgetDecision(False, "blocked by standard quality reserve", band)

        if band == HIGH_BAND and self.sent_count(band=HIGH_BAND, now=now) >= self.high_daily_cap:
            return PriorityBudgetDecision(False, "blocked by high quality reserve", band)

        return PriorityBudgetDecision(True, "allowed", band)

    def reserve(self, score: int, now: datetime | None = None) -> PriorityBudgetDecision:
        now = _normalize_now(now)
        decision = self.should_send(score, now=now)
        if decision.allowed:
            self.record_sent(score, now=now)
        return decision

    def release(self, score: int, now: datetime | None = None) -> None:
        now = _normalize_now(now)
        band = self.band_for_score(score)
        day_key = _day_key(now)
        self._sent_count_by_day[day_key] = max(0, self._sent_count_by_day.get(day_key, 0) - 1)
        band_key = (day_key, band)
        self._sent_count_by_day_and_band[band_key] = max(
            0,
            self._sent_count_by_day_and_band.get(band_key, 0) - 1,
        )

    def record_sent(self, score: int, now: datetime | None = None) -> None:
        now = _normalize_now(now)
        day_key = _day_key(now)
        band = self.band_for_score(score)
        self._sent_count_by_day[day_key] = self._sent_count_by_day.get(day_key, 0) + 1
        band_key = (day_key, band)
        self._sent_count_by_day_and_band[band_key] = self._sent_count_by_day_and_band.get(band_key, 0) + 1

    def sent_count(self, band: str | None = None, now: datetime | None = None) -> int:
        now = _normalize_now(now)
        day_key = _day_key(now)
        if band is None:
            return self._sent_count_by_day.get(day_key, 0)
        return self._sent_count_by_day_and_band.get((day_key, band), 0)

    def counts_by_band(self, now: datetime | None = None) -> dict[str, int]:
        now = _normalize_now(now)
        return {
            STANDARD_BAND: self.sent_count(STANDARD_BAND, now=now),
            HIGH_BAND: self.sent_count(HIGH_BAND, now=now),
            ELITE_BAND: self.sent_count(ELITE_BAND, now=now),
        }

    def band_for_score(self, score: int) -> str:
        if score >= self.elite_score:
            return ELITE_BAND
        if score >= self.high_score:
            return HIGH_BAND
        return STANDARD_BAND


def is_signal_alert_message(message: str) -> bool:
    text = _plain_text(message).lower()
    if "<code>" not in message.lower() and not _looks_like_token_address(text):
        return False
    return any(
        marker in text
        for marker in (
            "freshies",
            "fresh buys",
            "dormant",
            "migration",
            "bundle",
            "pattern",
            "sns",
            "vanish",
            "strong launch",
            "strong floor",
            "strongfloor",
            "streamflow",
            "dev held",
            "creator",
            "socials",
        )
    )


def score_v1_alert_message(message: str) -> int:
    """Estimate V1 alert quality from formatted Telegram text."""

    text = _plain_text(message)
    lower = text.lower()
    score = 45

    if "big dormant" in lower:
        score += 28
    elif "semi-dormant" in lower or "semi dormant" in lower:
        score += 24
    elif "dormant" in lower:
        score += 22

    if "freshies wizard" in lower or "fresh buys" in lower:
        score += 18
    elif "freshies" in lower:
        score += 14

    if "late migration" in lower or "migration" in lower:
        score += 20
    if "pattern" in lower:
        score += 16
    if "strong launch" in lower or "strong floor" in lower or "strongfloor" in lower:
        score += 14
    if "bundle" in lower:
        score += 12
    if "vanish" in lower or "sns" in lower:
        score += 10
    if "dev held" in lower or "streamflow" in lower or "creator" in lower:
        score += 8

    score += _sol_size_points(text)
    score += _market_cap_points(text)
    score += _age_points(text)
    score += _last_seen_points(text)
    score += _fresh_buy_points(text)

    if any(link_marker in lower for link_marker in ("photon", "axiom", "dexscreener", "bullx", "padre")):
        score += 4
    if "test alert" in lower or "**test" in lower:
        score -= 30
    if "unknown" in lower:
        score -= 4

    return max(0, min(100, score))


def _bounded_cap(value: int | None, default: int, daily_cap: int) -> int:
    cap = default if value is None else value
    if cap < 0:
        raise ValueError("band caps cannot be negative")
    return min(cap, daily_cap)


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _day_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _plain_text(message: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", message))


def _looks_like_token_address(text: str) -> bool:
    return bool(re.search(r"\b0x[a-f0-9]{32,}\b", text) or re.search(r"\b[1-9a-km-z]{32,}\b", text))


def _sol_size_points(text: str) -> int:
    values = [float(match.group(1)) for match in _SOL_RE.finditer(text)]
    if not values:
        return 0
    largest = max(values)
    if largest >= 5:
        return 20
    if largest >= 2:
        return 16
    if largest >= 1:
        return 12
    if largest >= 0.5:
        return 8
    return 4


def _market_cap_points(text: str) -> int:
    match = _MC_RE.search(text)
    value = _money_value(match) if match else _largest_compact_money(text)
    if value is None:
        return 0
    if 25_000 <= value <= 500_000:
        return 18
    if 500_000 < value <= 5_000_000:
        return 14
    if 5_000_000 < value <= 25_000_000:
        return 8
    if value < 25_000:
        return 4
    return 2


def _age_points(text: str) -> int:
    match = _AGE_RE.search(text)
    if not match:
        return 0
    value = int(match.group(1))
    unit = match.group(2).lower()
    minutes = value
    if unit == "h":
        minutes = value * 60
    elif unit == "d":
        minutes = value * 1440
    if minutes <= 60:
        return 12
    if minutes <= 360:
        return 8
    if minutes <= 1440:
        return 6
    return 2


def _last_seen_points(text: str) -> int:
    match = _LAST_SEEN_RE.search(text)
    if not match:
        return 0
    days = int(match.group(1))
    if days >= 30:
        return 18
    if days >= 8:
        return 12
    if days >= 4:
        return 8
    return 0


def _fresh_buy_points(text: str) -> int:
    values = [int(match.group(1)) for match in _FRESH_BUYS_RE.finditer(text)]
    if not values:
        return 0
    largest = max(values)
    if largest >= 10:
        return 10
    if largest >= 5:
        return 7
    if largest >= 2:
        return 4
    return 0


def _largest_compact_money(text: str) -> float | None:
    values = []
    for match in _MONEY_RE.finditer(text):
        suffix = match.group(2)
        if not suffix:
            continue
        values.append(_money_value(match))
    numeric_values = [value for value in values if value is not None]
    return max(numeric_values) if numeric_values else None


def _money_value(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    value = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "m":
        return value * 1_000_000
    if suffix == "k":
        return value * 1_000
    return value
