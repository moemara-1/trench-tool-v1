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


@dataclass
class RPCEndpoint:
    """Single RPC endpoint with stats tracking."""
    api_key: str
    request_count: int = 0
    error_count: int = 0
    last_429_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None

    @property
    def rpc_url(self) -> str:
        return f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"

    @property
    def ws_url(self) -> str:
        return f"wss://mainnet.helius-rpc.com/?api-key={self.api_key}"

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
    RATE_LIMIT_COOLDOWN_SEC = 5.0

    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("At least one Helius API key is required")

        self._endpoints = [RPCEndpoint(api_key=key.strip()) for key in api_keys if key.strip()]
        self._current_index = 0
        self._lock = threading.Lock()
        self._last_request_time = 0.0

        logger.info(f"🔄 HeliusRPCManager initialized with {len(self._endpoints)} endpoints (throttled)")
        for i, ep in enumerate(self._endpoints):
            logger.debug(f"  Endpoint {i+1}: ...{ep.api_key[-8:]}")
    
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

            # All endpoints in cooldown - use first one anyway
            endpoint = self._endpoints[0]
            endpoint.request_count += 1
            self._last_request_time = time.time()
            return endpoint.rpc_url
    
    def get_ws_url(self) -> str:
        """
        Get a WebSocket URL.
        For WebSocket, we typically want to stick with one connection,
        so this returns the first endpoint's WS URL.
        """
        return self._endpoints[0].ws_url
    
    def get_all_ws_urls(self) -> List[str]:
        """Get all WebSocket URLs for potential multi-connection setups."""
        return [ep.ws_url for ep in self._endpoints]
    
    def report_error(self, rpc_url: str, is_rate_limit: bool = False):
        """
        Report an error for a specific endpoint.
        Sets cooldown period for rate-limited endpoints.
        """
        with self._lock:
            for endpoint in self._endpoints:
                if endpoint.rpc_url == rpc_url:
                    endpoint.error_count += 1
                    if is_rate_limit:
                        endpoint.last_429_time = datetime.utcnow()
                        endpoint.set_cooldown(self.RATE_LIMIT_COOLDOWN_SEC)
                        logger.warning(f"⚠️ Rate limit hit on endpoint ...{endpoint.api_key[-8:]}, cooldown {self.RATE_LIMIT_COOLDOWN_SEC}s")
                    break
    
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
                        "key_suffix": f"...{ep.api_key[-8:]}",
                        "requests": ep.request_count,
                        "errors": ep.error_count,
                        "last_429": ep.last_429_time.isoformat() if ep.last_429_time else None,
                    }
                    for ep in self._endpoints
                ]
            }


# Singleton instance
_rpc_manager: Optional[HeliusRPCManager] = None


def init_rpc_manager(api_keys: List[str]) -> HeliusRPCManager:
    """Initialize the global RPC manager with API keys."""
    global _rpc_manager
    _rpc_manager = HeliusRPCManager(api_keys)
    return _rpc_manager


def get_rpc_manager() -> HeliusRPCManager:
    """Get the global RPC manager instance."""
    global _rpc_manager
    if _rpc_manager is None:
        # Fallback: try to initialize from settings
        from config import settings
        api_keys = settings.helius_api_keys
        if not api_keys:
            # Ultimate fallback: extract from legacy URL
            rpc_url = settings.solana_rpc_url
            if "api-key=" in rpc_url:
                key = rpc_url.split("api-key=")[-1]
                api_keys = [key]
            else:
                raise ValueError("No Helius API keys configured")
        _rpc_manager = HeliusRPCManager(api_keys)
    return _rpc_manager
