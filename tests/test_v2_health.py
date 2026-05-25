from datetime import datetime, timedelta, timezone

from trench_v2.core.models import ProviderHealth
from trench_v2.engine.health import HealthMonitor, IngestionState


def test_health_is_unhealthy_when_ingestion_is_stale():
    health = HealthMonitor(
        providers=[ProviderHealth(name="helius", ok=True)],
        ingestion=IngestionState(
            last_event_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            queue_depth=0,
            processed_events=100,
        ),
        max_ingestion_lag_seconds=300,
    ).snapshot()

    assert health.ok is False
    assert any("stale" in reason.lower() for reason in health.reasons)


def test_health_is_unhealthy_when_provider_is_rate_limited():
    health = HealthMonitor(
        providers=[
            ProviderHealth(
                name="helius",
                ok=False,
                rate_limited=True,
                detail="HTTP 429",
            )
        ],
        ingestion=IngestionState(
            last_event_at=datetime.now(timezone.utc),
            queue_depth=2,
            processed_events=10,
        ),
    ).snapshot()

    assert health.ok is False
    assert any("rate limited" in reason.lower() for reason in health.reasons)


def test_health_is_healthy_when_providers_and_ingestion_are_fresh():
    health = HealthMonitor(
        providers=[ProviderHealth(name="alchemy", ok=True)],
        ingestion=IngestionState(
            last_event_at=datetime.now(timezone.utc),
            queue_depth=1,
            processed_events=10,
        ),
    ).snapshot()

    assert health.ok is True
    assert health.reasons == []
