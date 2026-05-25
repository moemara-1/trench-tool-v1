"""FastAPI surface for V2 side-by-side deployment."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from trench_v2.config import V2Settings
from trench_v2.core.feature_catalog import FeatureCatalog
from trench_v2.core.feature_status import FeatureReadinessService
from trench_v2.core.models import Chain
from trench_v2.engine.health import HealthMonitor, IngestionState
from trench_v2.engine.live_signals import LiveSignalWorker
from trench_v2.engine.watchlist import InMemoryWatchlist
from trench_v2.providers.factory import build_scanner
from trench_v2.providers.health import ProviderHealthService
from trench_v2.telegram.commands import CommandRouter
from trench_v2.telegram.topics import build_default_topic_plan, working_topic_ids


class TelegramCommandRequest(BaseModel):
    text: str


def create_app(settings: V2Settings | None = None) -> FastAPI:
    app_settings = settings
    initial_settings = app_settings or V2Settings.from_env(os.environ)
    scanner = build_scanner(initial_settings)
    watchlist = InMemoryWatchlist()
    commands = CommandRouter(scanner=scanner, watchlist=watchlist)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_settings = app_settings or V2Settings.from_env(os.environ)
        worker = LiveSignalWorker(runtime_settings)
        app.state.signal_worker = worker
        await worker.start()
        try:
            yield
        finally:
            await worker.stop()

    app = FastAPI(
        title="Trench Tool V2",
        description="Private Telegram-first scanner and alert engine",
        version="2.0.0-foundation",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict:
        runtime_settings = app_settings or V2Settings.from_env(os.environ)
        providers = await ProviderHealthService(runtime_settings).check()
        snapshot = HealthMonitor(
            providers=providers,
            ingestion=IngestionState(
                last_event_at=datetime.now(timezone.utc),
                queue_depth=0,
                processed_events=0,
            ),
        ).snapshot()
        return {
            "ok": snapshot.ok,
            "reasons": snapshot.reasons,
            "queue_depth": snapshot.queue_depth,
            "processed_events": snapshot.processed_events,
            "providers": [
                {
                    "name": provider.name,
                    "ok": provider.ok,
                    "rate_limited": provider.rate_limited,
                    "detail": provider.detail,
                }
                for provider in snapshot.providers
            ],
        }

    @app.get("/v2/scan/{chain}/{address}")
    async def scan_token(chain: str, address: str) -> dict:
        try:
            token_scan = await scanner.scan(address, Chain.from_hint(chain))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "chain": token_scan.chain.value,
            "address": token_scan.address,
            "symbol": token_scan.symbol,
            "name": token_scan.name,
            "market_cap_usd": token_scan.market_cap_usd,
            "liquidity_usd": token_scan.liquidity_usd,
            "risk": {
                "level": token_scan.risk.level.value,
                "is_honeypot": token_scan.risk.is_honeypot,
                "buy_tax_bps": token_scan.risk.buy_tax_bps,
                "sell_tax_bps": token_scan.risk.sell_tax_bps,
                "liquidity_locked": token_scan.risk.liquidity_locked,
                "delayed_honeypot": token_scan.risk.delayed_honeypot,
                "malicious_contract": token_scan.risk.malicious_contract,
                "liquidity_pull_risk": token_scan.risk.liquidity_pull_risk,
                "reasons": token_scan.risk.reasons,
            },
            "signals": {
                "confidence": token_scan.signals.confidence,
                "risk": token_scan.signals.risk,
                "reasons": token_scan.signals.reasons,
            },
            "holder_clusters": [
                {
                    "label": cluster.label,
                    "wallets": cluster.wallets,
                    "supply_percent": cluster.supply_percent,
                    "evidence": cluster.evidence,
                }
                for cluster in token_scan.holder_clusters
            ],
        }

    @app.post("/v2/telegram/command")
    async def telegram_command(request: TelegramCommandRequest) -> dict:
        try:
            response = await commands.handle(request.text)
        except ValueError as exc:
            return {"ok": False, "text": str(exc), "parse_mode": "HTML"}

        return {
            "ok": response.ok,
            "text": response.text,
            "parse_mode": response.parse_mode,
        }

    @app.get("/v2/features")
    async def list_features() -> dict:
        runtime_settings = app_settings or V2Settings.from_env(os.environ)
        catalog = FeatureCatalog.default()
        readiness_service = FeatureReadinessService(runtime_settings, catalog=catalog)
        active_topic_keys = {target.env_key for target in build_default_topic_plan()}
        return {
            "features": [
                _feature_payload(spec, catalog, active_topic_keys, readiness_service)
                for spec in catalog.all()
            ]
        }

    @app.get("/v2/topics")
    async def list_topics() -> dict:
        runtime_settings = app_settings or V2Settings.from_env(os.environ)
        configured = working_topic_ids(runtime_settings)
        topics = [
            {
                "chain": target.chain.value,
                "feature": target.feature.value,
                "title": target.title,
                "env_key": target.env_key,
                "configured": target.env_key in configured,
            }
            for target in build_default_topic_plan()
        ]
        return {
            "configured_count": sum(1 for topic in topics if topic["configured"]),
            "missing_count": sum(1 for topic in topics if not topic["configured"]),
            "topics": topics,
        }

    @app.get("/v2/signals")
    async def live_signals_status() -> dict:
        worker = getattr(app.state, "signal_worker", None)
        if worker is None:
            return {"running": False, "last_error": "worker not initialized"}
        return worker.stats.as_dict()

    @app.get("/v2/watchlist")
    async def list_watchlist() -> dict:
        return {
            "targets": [
                {
                    "id": target.id,
                    "chain": target.chain.value,
                    "address": target.address,
                    "created_at": target.created_at.isoformat(),
                    "note": target.note,
                }
                for target in watchlist.list_targets()
            ]
        }

    return app


app = create_app()


def _feature_payload(
    spec,
    catalog: FeatureCatalog,
    active_topic_keys: set[str],
    readiness_service: FeatureReadinessService,
) -> dict:
    readiness = readiness_service.for_feature(spec.id)
    topic_key = catalog.topic_env_key(spec.id) if spec.chain else None
    return {
        "id": spec.id,
        "title": spec.title,
        "kind": spec.kind.value,
        "chain": spec.chain.value if spec.chain else None,
        "topic_feature": spec.topic_feature.value,
        "topic_env_key": topic_key,
        "telegram_topic_active": topic_key in active_topic_keys if topic_key else False,
        "implementation_status": readiness.status,
        "blocked_on": readiness.blocked_on,
        "source": spec.source,
        "min_native_amount": spec.min_native_amount,
        "max_market_cap_usd": spec.max_market_cap_usd,
        "min_inactive_days": spec.min_inactive_days,
        "min_wallets": spec.min_wallets,
        "notes": spec.notes,
    }
