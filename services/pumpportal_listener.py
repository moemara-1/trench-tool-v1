"""Low-volume PumpPortal stream for free Pump.fun creation and migration events."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"

EventHandler = Callable[["PumpPortalEvent"], Awaitable[None]]
RunningCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class PumpPortalEvent:
    """A validated creation or migration event from PumpPortal."""

    kind: str
    mint: str
    symbol: str
    name: str
    creator_wallet: str | None
    signature: str | None
    initial_buy_sol: float | None
    market_cap_sol: float | None
    pool: str | None


class PumpPortalListener:
    """Maintain one PumpPortal websocket for free creation and migration data."""

    def __init__(
        self,
        ws_url: str = PUMPPORTAL_WS_URL,
        api_key: str = "",
        reconnect_min_seconds: float = 5.0,
        reconnect_max_seconds: float = 60.0,
    ) -> None:
        if reconnect_min_seconds <= 0:
            raise ValueError("reconnect_min_seconds must be positive")
        if reconnect_max_seconds < reconnect_min_seconds:
            raise ValueError("reconnect_max_seconds must be >= reconnect_min_seconds")

        self._ws_url = ws_url.rstrip("?")
        self._api_key = api_key.strip()
        self._reconnect_min_seconds = reconnect_min_seconds
        self._reconnect_max_seconds = reconnect_max_seconds
        self._connected = False
        self._connections = 0
        self._reconnects = 0
        self._messages_received = 0
        self._events_received = 0
        self._events_by_kind: dict[str, int] = defaultdict(int)
        self._ignored_messages = 0
        self._duplicate_events = 0
        self._callback_errors = 0
        self._last_event_at: datetime | None = None
        self._last_connected_at: datetime | None = None
        self._last_error: str | None = None
        self._seen_event_keys: set[str] = set()

    @property
    def connection_url(self) -> str:
        if not self._api_key:
            return self._ws_url
        separator = "&" if "?" in self._ws_url else "?"
        return f"{self._ws_url}{separator}{urlencode({'api-key': self._api_key})}"

    def parse_event(self, payload: Mapping[str, object] | str | bytes) -> PumpPortalEvent | None:
        """Return only validated creation and migration events."""

        data = _coerce_payload(payload)
        if data is None:
            return None

        kind = _event_kind(data.get("txType"))
        mint = _clean_string(data.get("mint"))
        if kind is None or mint is None:
            return None

        return PumpPortalEvent(
            kind=kind,
            mint=mint,
            symbol=_clean_string(data.get("symbol")) or "UNKNOWN",
            name=_clean_string(data.get("name")) or _clean_string(data.get("symbol")) or "Unknown Token",
            creator_wallet=_clean_string(data.get("traderPublicKey")),
            signature=_clean_string(data.get("signature")),
            initial_buy_sol=_finite_float(data.get("initialBuy")),
            market_cap_sol=_finite_float(data.get("marketCapSol")),
            pool=_clean_string(data.get("pool")),
        )

    async def run(self, on_event: EventHandler, is_running: RunningCheck) -> None:
        """Connect once, subscribe to the free streams, and reconnect with backoff."""

        import websockets

        backoff = self._reconnect_min_seconds
        while is_running():
            try:
                async with websockets.connect(
                    self.connection_url,
                    ping_interval=25,
                    ping_timeout=20,
                    close_timeout=10,
                    max_size=1_000_000,
                ) as websocket:
                    self._connected = True
                    self._connections += 1
                    self._last_connected_at = datetime.utcnow()
                    self._last_error = None
                    await self._subscribe(websocket)
                    backoff = self._reconnect_min_seconds
                    logger.info("PumpPortal connected; subscribed to creation and migration events")

                    async for raw_message in websocket:
                        if not is_running():
                            break
                        self._messages_received += 1
                        event = self.parse_event(raw_message)
                        if event is None:
                            self._ignored_messages += 1
                            continue
                        if self._is_duplicate(event):
                            self._duplicate_events += 1
                            continue

                        self._events_received += 1
                        self._events_by_kind[event.kind] += 1
                        self._last_event_at = datetime.utcnow()
                        try:
                            await on_event(event)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            self._callback_errors += 1
                            logger.exception("PumpPortal event callback failed")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = type(exc).__name__
                if not is_running():
                    break
                self._reconnects += 1
                logger.warning(
                    "PumpPortal connection failed (%s); reconnecting in %.0fs",
                    self._last_error,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(self._reconnect_max_seconds, backoff * 2)
            finally:
                self._connected = False

    async def _subscribe(self, websocket: object) -> None:
        send = getattr(websocket, "send")
        await send(json.dumps({"method": "subscribeNewToken"}))
        await send(json.dumps({"method": "subscribeMigration"}))

    def _is_duplicate(self, event: PumpPortalEvent) -> bool:
        key = f"{event.kind}:{event.mint}:{event.signature or ''}"
        if key in self._seen_event_keys:
            return True
        if len(self._seen_event_keys) >= 5_000:
            self._seen_event_keys.clear()
        self._seen_event_keys.add(key)
        return False

    def get_stats(self) -> dict:
        return {
            "connected": self._connected,
            "connections": self._connections,
            "reconnects": self._reconnects,
            "messages_received": self._messages_received,
            "events_received": self._events_received,
            "events_by_kind": dict(sorted(self._events_by_kind.items())),
            "ignored_messages": self._ignored_messages,
            "duplicate_events": self._duplicate_events,
            "callback_errors": self._callback_errors,
            "last_event_at": _iso_or_none(self._last_event_at),
            "last_connected_at": _iso_or_none(self._last_connected_at),
            "last_error": self._last_error,
        }


def _coerce_payload(payload: Mapping[str, object] | str | bytes) -> Mapping[str, object] | None:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if not isinstance(payload, str):
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _event_kind(value: object) -> str | None:
    tx_type = _clean_string(value)
    if tx_type is None:
        return None
    normalized = tx_type.lower()
    if normalized in {"create", "new_token", "newtoken"}:
        return "new_token"
    if normalized in {"migrate", "migration"}:
        return "migration"
    return None


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None