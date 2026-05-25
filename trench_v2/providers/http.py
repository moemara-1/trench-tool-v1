"""HTTP helpers with explicit provider-rate-limit behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

import httpx


class ProviderRateLimitError(RuntimeError):
    """Raised when an upstream provider returns HTTP 429."""


@dataclass(slots=True)
class ProviderCircuitBreaker:
    """Small circuit breaker for provider backoff."""

    name: str
    cooldown_seconds: int = 60
    cooldown_until: Optional[datetime] = None
    last_error: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.cooldown_until is not None and datetime.now(timezone.utc) < self.cooldown_until

    def record_success(self) -> None:
        self.cooldown_until = None
        self.last_error = None

    def record_rate_limit(self, detail: str = "HTTP 429") -> None:
        self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=self.cooldown_seconds)
        self.last_error = detail


class AsyncJsonClient:
    """Tiny JSON client wrapper used by real providers."""

    def __init__(
        self,
        name: str,
        timeout_seconds: float = 15.0,
        headers: Mapping[str, str] | None = None,
    ):
        self.name = name
        self.breaker = ProviderCircuitBreaker(name=name)
        self._timeout_seconds = timeout_seconds
        self._headers = dict(headers or {})

    async def get_json(self, url: str, params: Mapping[str, str] | None = None) -> dict | list:
        if self.breaker.is_open:
            raise ProviderRateLimitError(f"{self.name} cooling down after {self.breaker.last_error}")

        async with httpx.AsyncClient(timeout=self._timeout_seconds, headers=self._headers) as client:
            response = await client.get(url, params=params)

        if response.status_code == 429:
            self.breaker.record_rate_limit()
            raise ProviderRateLimitError(f"{self.name} returned HTTP 429")

        response.raise_for_status()
        self.breaker.record_success()
        data = response.json()
        if not isinstance(data, (dict, list)):
            raise ValueError(f"{self.name} returned non-object/list JSON")
        return data

    async def post_json(self, url: str, payload: Mapping[str, object]) -> dict:
        if self.breaker.is_open:
            raise ProviderRateLimitError(f"{self.name} cooling down after {self.breaker.last_error}")

        async with httpx.AsyncClient(timeout=self._timeout_seconds, headers=self._headers) as client:
            response = await client.post(url, json=dict(payload))

        if response.status_code == 429:
            self.breaker.record_rate_limit()
            raise ProviderRateLimitError(f"{self.name} returned HTTP 429")

        response.raise_for_status()
        self.breaker.record_success()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"{self.name} returned non-object JSON")
        return data
