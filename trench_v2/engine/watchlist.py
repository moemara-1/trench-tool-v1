"""Private in-memory watchlist for V2 commands.

This is intentionally simple for the first side-by-side V2 milestone. A durable
repository can replace it without changing the Telegram command surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trench_v2.chains.adapters import default_registry
from trench_v2.core.models import Chain, WatchTarget


class InMemoryWatchlist:
    def __init__(self):
        self._targets: dict[str, WatchTarget] = {}

    async def track(self, address: str, chain: Chain | None = None) -> str:
        resolved = default_registry.resolve(address, chain)
        target_id = f"{resolved.value}:{address.lower()}"
        self._targets[target_id] = WatchTarget(
            id=target_id,
            chain=resolved,
            address=address,
            created_at=datetime.now(timezone.utc),
        )
        return target_id

    async def watch(self, address: str, chain: Chain | None = None) -> str:
        return await self.track(address, chain)

    def list_targets(self) -> list[WatchTarget]:
        return list(self._targets.values())

