"""Health contract for V2 runtime and providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from trench_v2.core.models import ProviderHealth, SystemHealth


@dataclass(slots=True)
class IngestionState:
    last_event_at: Optional[datetime]
    queue_depth: int
    processed_events: int


class HealthMonitor:
    """Reports whether V2 is doing useful work."""

    def __init__(
        self,
        providers: list[ProviderHealth],
        ingestion: IngestionState,
        max_ingestion_lag_seconds: int = 300,
    ):
        self.providers = providers
        self.ingestion = ingestion
        self.max_ingestion_lag_seconds = max_ingestion_lag_seconds

    def snapshot(self) -> SystemHealth:
        reasons: list[str] = []
        lag_seconds: Optional[float] = None

        if self.ingestion.last_event_at is None:
            reasons.append("Ingestion has not processed an event")
        else:
            now = datetime.now(timezone.utc)
            last_event = self.ingestion.last_event_at
            if last_event.tzinfo is None:
                last_event = last_event.replace(tzinfo=timezone.utc)
            lag_seconds = (now - last_event).total_seconds()
            if lag_seconds > self.max_ingestion_lag_seconds:
                reasons.append(f"Ingestion stale for {int(lag_seconds)}s")

        for provider in self.providers:
            if provider.rate_limited:
                reasons.append(f"Provider {provider.name} is rate limited")
            elif not provider.ok:
                detail = f": {provider.detail}" if provider.detail else ""
                reasons.append(f"Provider {provider.name} unhealthy{detail}")

        return SystemHealth(
            ok=len(reasons) == 0,
            reasons=reasons,
            providers=self.providers,
            ingestion_lag_seconds=lag_seconds,
            queue_depth=self.ingestion.queue_depth,
            processed_events=self.ingestion.processed_events,
        )

