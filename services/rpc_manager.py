"""
Helius RPC Manager - Multi-endpoint rotation for rate limit avoidance.
Rotates between multiple free Helius RPC endpoints to maximize throughput.
Includes adaptive throttling when rate limits are hit.
"""

import asyncio
import logging
import threading
import time
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
class RPCUnavailableError(RuntimeError):
    """Raised when every RPC endpoint is cooling down after provider failures."""

    def __init__(self, retry_after: float):
        self.retry_after = max(0.0, retry_after)
        super().__init__(f"all RPC endpoints are cooling; retry after {self.retry_after:.1f}s")


@dataclass
class RPCEndpoint:
    """Single RPC endpoint with stats tracking."""
    api_key: str = ""
    rpc_url_override: str | None = None
    ws_url_override: str | None = None
    supports_log_subscriptions: bool = True
    request_count: int = 0
    error_count: int = 0
    last_429_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    consecutive_rate_limits: int = 0

    @property
    def rpc_url(self) -> str:
        if self.rpc_url_override:
            return self.rpc_url_override
        return f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"

    @property
    def ws_url(self) -> str:
        if self.ws_url_override:
            return self.ws_url_override
        return f"wss://mainnet.helius-rpc.com/?api-key={self.api_key}"

    @property
    def label(self) -> str:
        if self.api_key:
            return f"...{self.api_key[-8:]}"
        return self.rpc_url.split("//", 1)[-1].split("/", 1)[0]

    @property
    def is_available(self) -> bool:
        """Check if endpoint is available (not in cooldown)."""
        if self.cooldown_until is None:
            return True
        return datetime.utcnow() >= self.cooldown_until

    def set_cooldown(self, seconds: float = 2.0):
        """Set cooldown period after rate limit hit."""
        self.cooldown_until = datetime.utcnow() + timedelta(seconds=seconds)


class HeliusRPCManager:
    """
    Thread-safe RPC endpoint rotation manager.
    Rotates between multiple Helius API keys to avoid rate limiting.

    Free tier: 10 RPC requests/second per key
    With 5 keys: 50 RPC requests/second total capacity

    Includes adaptive throttling:
    - 100ms minimum between requests per endpoint
    - 2 second cooldown after 429 error
    - Skips endpoints in cooldown
    """

    # Minimum time between requests globally (ms)
    # With 4 keys at 10 req/s each = 40 req/s total
    # 100ms interval = 10 req/s max, should stay under limit
    MIN_REQUEST_INTERVAL_MS = 100
    # Cooldown duration after rate limit (seconds)
    RATE_LIMIT_COOLDOWN_SEC = 60.0
    RATE_LIMIT_MAX_COOLDOWN_SEC = 3600.0

    def __init__(
        self,
        api_keys: List[str],
        fallback_rpc_url: str | None = None,
        fallback_ws_url: str | None = None,
        fallback_ws_supports_log_subscriptions: bool = False,
        prefer_fallback_rpc: bool = False,
    ):
        self._endpoints = [RPCEndpoint(api_key=key.strip()) for key in api_keys if key.strip()]
        if fallback_rpc_url and fallback_ws_url:
            fallback_endpoint = RPCEndpoint(
                rpc_url_override=fallback_rpc_url.strip(),
                ws_url_override=fallback_ws_url.strip(),
                supports_log_subscriptions=fallback_ws_supports_log_subscriptions,
            )
            if prefer_fallback_rpc:
                self._endpoints.insert(0, fallback_endpoint)
            else:
                self._endpoints.append(fallback_endpoint)
        if not self._endpoints:
            raise ValueError("At least one Solana RPC endpoint is required")
        self._current_index = 0
        self._lock = threading.Lock()
        self._last_request_time = 0.0

        logger.info(f"🔄 HeliusRPCManager initialized with {len(self._endpoints)} endpoints (throttled)")
        for i, ep in enumerate(self._endpoints):
            logger.debug(f"  Endpoint {i+1}: {ep.label}")
    
    @property
    def endpoint_count(self) -> int:
        """Number of available endpoints."""
        return len(self._endpoints)
    
    def get_rpc_url(self) -> str:
        """
        Get the next available RPC URL in round-robin rotation.
        Thread-safe. Respects cooldowns and adds minimum delay.
        """
        with self._lock:
            # Enforce minimum delay between requests
            now = time.time()
            elapsed_ms = (now - self._last_request_time) * 1000
            if elapsed_ms < self.MIN_REQUEST_INTERVAL_MS:
                time.sleep((self.MIN_REQUEST_INTERVAL_MS - elapsed_ms) / 1000)

            # Find next available endpoint (not in cooldown)
            attempts = 0
            while attempts < len(self._endpoints):
                endpoint = self._endpoints[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._endpoints)

                if endpoint.is_available:
                    endpoint.request_count += 1
                    self._last_request_time = time.time()
                    return endpoint.rpc_url

                attempts += 1

            # Do not sleep in this synchronous selector: it is called from the
            # FastAPI event loop. Callers should skip work until an endpoint is ready.
            retry_after = self._seconds_until_available_unlocked()
            if retry_after <= 0:
                endpoint = self._next_endpoint_by_cooldown()
                endpoint.request_count += 1
                self._last_request_time = time.time()
                return endpoint.rpc_url
            raise RPCUnavailableError(retry_after)
    
    def get_ws_url(self) -> str:
        """
        Get a log-capable WebSocket URL.

        HTTP-only fallback providers remain available for RPC calls but are
        never selected for logsSubscribe.
        """
        with self._lock:
            websocket_endpoints = [
                endpoint
                for endpoint in self._endpoints
                if endpoint.supports_log_subscriptions
            ]
            if not websocket_endpoints:
                raise RuntimeError("No Solana websocket endpoint supports logsSubscribe")

            attempts = 0
            while attempts < len(self._endpoints):
                endpoint = self._endpoints[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._endpoints)
                if endpoint.supports_log_subscriptions and endpoint.is_available:
                    return endpoint.ws_url
                attempts += 1

            endpoint = min(
                websocket_endpoints,
                key=lambda candidate: candidate.cooldown_until or datetime.utcnow(),
            )
            logger.warning(
                "All log-capable websocket endpoints cooling down; retrying the earliest endpoint"
            )
            return endpoint.ws_url
    def get_all_ws_urls(self) -> List[str]:
        """Get all WebSocket URLs for potential multi-connection setups."""
        return [ep.ws_url for ep in self._endpoints if ep.supports_log_subscriptions]
    
    def report_error(self, rpc_url: str, is_rate_limit: bool = False):
        """
        Report an error for a specific endpoint.
        Sets cooldown period for rate-limited endpoints.
        """
        with self._lock:
            for endpoint in self._endpoints:
                if endpoint.rpc_url == rpc_url or endpoint.ws_url == rpc_url:
                    endpoint.error_count += 1
                    if is_rate_limit:
                        endpoint.last_429_time = datetime.utcnow()
                        endpoint.consecutive_rate_limits += 1
                        cooldown_seconds = min(
                            self.RATE_LIMIT_COOLDOWN_SEC * (2 ** (endpoint.consecutive_rate_limits - 1)),
                            self.RATE_LIMIT_MAX_COOLDOWN_SEC,
                        )
                        endpoint.set_cooldown(cooldown_seconds)
                        logger.warning(
                            f"Rate limit hit on endpoint ...{endpoint.api_key[-8:]}, "
                            f"cooldown {cooldown_seconds}s"
                        )
                    else:
                        endpoint.consecutive_rate_limits = 0
                    break

    def seconds_until_available(self) -> float:
        """Seconds until any endpoint leaves cooldown, or 0 if one is ready."""
        with self._lock:
            return self._seconds_until_available_unlocked()

    def _seconds_until_available_unlocked(self) -> float:
        if any(endpoint.is_available for endpoint in self._endpoints):
            return 0.0
        now = datetime.utcnow()
        waits = [
            max(0.0, (endpoint.cooldown_until - now).total_seconds())
            for endpoint in self._endpoints
            if endpoint.cooldown_until is not None
        ]
        return min(waits) if waits else 0.0


    def _next_endpoint_by_cooldown(self) -> RPCEndpoint:
        return min(
            self._endpoints,
            key=lambda endpoint: endpoint.cooldown_until or datetime.utcnow(),
        )
    
    def get_stats(self) -> dict:
        """Get usage statistics for all endpoints."""
        with self._lock:
            total_requests = sum(ep.request_count for ep in self._endpoints)
            total_errors = sum(ep.error_count for ep in self._endpoints)
            
            return {
                "total_endpoints": len(self._endpoints),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "endpoints": [
                    {
                        "key_suffix": ep.label,
                        "requests": ep.request_count,
                        "errors": ep.error_count,
                        "last_429": ep.last_429_time.isoformat() if ep.last_429_time else None,
                        "supports_log_subscriptions": ep.supports_log_subscriptions,
                    }
                    for ep in self._endpoints
                ]
            }


# Singleton instance
_rpc_manager: Optional[HeliusRPCManager] = None


def init_rpc_manager(
    api_keys: List[str],
    fallback_rpc_url: str | None = None,
    fallback_ws_url: str | None = None,
    fallback_ws_supports_log_subscriptions: bool = False,
    prefer_fallback_rpc: bool = False,
) -> HeliusRPCManager:
    """Initialize the global RPC manager with API keys."""
    global _rpc_manager
    _rpc_manager = HeliusRPCManager(
        api_keys,
        fallback_rpc_url,
        fallback_ws_url,
        fallback_ws_supports_log_subscriptions=fallback_ws_supports_log_subscriptions,
        prefer_fallback_rpc=prefer_fallback_rpc,
    )
    return _rpc_manager


def get_rpc_manager() -> HeliusRPCManager:
    """Get the global RPC manager instance."""
    global _rpc_manager
    if _rpc_manager is None:
        # Fallback: try to initialize from settings
        from config import settings
        api_keys = settings.helius_api_keys
        fallback_rpc_url = _generic_fallback_url(settings.solana_rpc_url)
        fallback_ws_url = _generic_fallback_url(settings.solana_ws_url)
        if not api_keys and not (fallback_rpc_url and fallback_ws_url):
            # Ultimate fallback: extract from legacy URL
            rpc_url = settings.solana_rpc_url
            if "api-key=" in rpc_url:
                key = rpc_url.split("api-key=")[-1]
                api_keys = [key]
            else:
                raise ValueError("No Helius API keys configured")
        _rpc_manager = HeliusRPCManager(
            api_keys,
            fallback_rpc_url,
            fallback_ws_url,
            fallback_ws_supports_log_subscriptions=settings.solana_fallback_ws_supports_log_subscriptions,
            prefer_fallback_rpc=settings.solana_prefer_fallback_rpc,
        )
    return _rpc_manager


def _generic_fallback_url(url: str) -> str | None:
    if not url:
        return None
    if "mainnet.helius-rpc.com" in url:
        return None
    return url
