"""Low-noise alert delivery policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from trench_v2.core.models import TokenScan


@dataclass(slots=True)
class AlertPolicyResult:
    allowed: bool
    reason: str


class LowNoiseAlertPolicy:
    """Enforce dedupe, cooldowns, and daily alert volume limits."""

    def __init__(self, daily_cap: int = 30, cooldown_seconds: int = 900):
        if daily_cap < 1:
            raise ValueError("daily_cap must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")

        self.daily_cap = daily_cap
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._sent_at_by_key: dict[str, datetime] = {}
        self._sent_count_by_day: dict[str, int] = {}

    def should_send(self, scan: TokenScan, topic: str, now: datetime | None = None) -> AlertPolicyResult:
        now = self._normalize_now(now)
        key = self._key(scan, topic)
        day_key = now.strftime("%Y-%m-%d")

        last_sent = self._sent_at_by_key.get(key)
        if last_sent and now - last_sent < self.cooldown:
            return AlertPolicyResult(False, "blocked by cooldown")

        if self._sent_count_by_day.get(day_key, 0) >= self.daily_cap:
            return AlertPolicyResult(False, "blocked by daily cap")

        return AlertPolicyResult(True, "allowed")

    def record_sent(self, scan: TokenScan, topic: str, now: datetime | None = None) -> None:
        now = self._normalize_now(now)
        key = self._key(scan, topic)
        day_key = now.strftime("%Y-%m-%d")
        self._sent_at_by_key[key] = now
        self._sent_count_by_day[day_key] = self._sent_count_by_day.get(day_key, 0) + 1

    def _key(self, scan: TokenScan, topic: str) -> str:
        return f"{topic}:{scan.chain.value}:{scan.address.lower()}"

    def _normalize_now(self, now: datetime | None) -> datetime:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
