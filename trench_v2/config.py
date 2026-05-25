"""V2 runtime configuration.

Secrets are read from environment variables only. This module deliberately
supports V1 variable names so V2 can be deployed side-by-side without copying
secret values into the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from trench_v2.core.models import Chain


@dataclass(frozen=True, slots=True)
class V2Settings:
    alchemy_api_key: str | None = None
    goplus_api_key: str | None = None
    honeypot_api_key: str | None = None
    etherscan_api_key: str | None = None
    moralis_api_key: str | None = None
    bitquery_api_key: str | None = None
    helius_api_keys: tuple[str, ...] = ()
    solana_rpc_url: str | None = None
    solana_ws_url: str | None = None
    eth_rpc_url: str | None = None
    base_rpc_url: str | None = None
    bsc_rpc_url: str | None = None
    bsc_ws_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_topic_ids: dict[str, int] | None = None
    database_url: str | None = None
    redis_url: str | None = None
    signal_worker_enabled: bool = True
    signal_poll_seconds: int = 300
    signal_max_alerts_per_cycle: int = 14
    signal_daily_cap: int = 30
    signal_min_quality: int = 82
    best_signals_daily_cap: int = 7
    best_signals_min_score: int = 95
    solana_provider_health_enabled: bool = False
    command_providers_enabled: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "V2Settings":
        alchemy_api_key = _blank_to_none(env.get("ALCHEMY_API_KEY"))
        return cls(
            alchemy_api_key=alchemy_api_key,
            goplus_api_key=_blank_to_none(env.get("GOPLUS_API_KEY")),
            honeypot_api_key=_blank_to_none(env.get("HONEYPOT_API_KEY")),
            etherscan_api_key=_blank_to_none(env.get("ETHERSCAN_API_KEY")),
            moralis_api_key=_blank_to_none(env.get("MORALIS_API_KEY")),
            bitquery_api_key=_blank_to_none(env.get("BITQUERY_API_KEY")),
            helius_api_keys=_split_keys(env.get("HELIUS_API_KEYS") or env.get("HELIUS_API_KEY")),
            solana_rpc_url=_blank_to_none(env.get("SOLANA_RPC_URL")),
            solana_ws_url=_blank_to_none(env.get("SOLANA_WS_URL")),
            eth_rpc_url=_blank_to_none(env.get("ETH_RPC_URL") or env.get("ALCHEMY_ETH_RPC_URL")),
            base_rpc_url=_blank_to_none(env.get("BASE_RPC_URL") or env.get("ALCHEMY_BASE_RPC_URL")),
            bsc_rpc_url=_blank_to_none(
                env.get("BSC_RPC_URL")
                or env.get("BSC_BSC_RPC_URL")
                or env.get("ALCHEMY_BSC_RPC_URL")
            ),
            bsc_ws_url=_blank_to_none(env.get("BSC_WS_URL") or env.get("BSC_BSC_WS_URL")),
            telegram_bot_token=_blank_to_none(env.get("TELEGRAM_BOT_TOKEN")),
            telegram_chat_id=_blank_to_none(env.get("TELEGRAM_CHAT_ID")),
            telegram_topic_ids=_topic_ids_from_env(env),
            database_url=_blank_to_none(env.get("DATABASE_URL")),
            redis_url=_blank_to_none(env.get("REDIS_URL")),
            signal_worker_enabled=_env_bool(env.get("V2_SIGNAL_WORKER_ENABLED"), default=True),
            signal_poll_seconds=_env_int(env.get("V2_SIGNAL_POLL_SECONDS"), default=300),
            signal_max_alerts_per_cycle=_env_int(env.get("V2_SIGNAL_MAX_ALERTS_PER_CYCLE"), default=14),
            signal_daily_cap=_env_int(env.get("V2_SIGNAL_DAILY_CAP"), default=30),
            signal_min_quality=_env_int(env.get("V2_SIGNAL_MIN_QUALITY"), default=82),
            best_signals_daily_cap=_env_int(env.get("BEST_SIGNALS_DAILY_CAP"), default=7),
            best_signals_min_score=_env_int(env.get("BEST_SIGNALS_MIN_SCORE"), default=95),
            solana_provider_health_enabled=_env_bool(
                env.get("V2_SOLANA_PROVIDER_HEALTH_ENABLED"),
                default=False,
            ),
            command_providers_enabled=_env_bool(
                env.get("V2_COMMAND_PROVIDERS_ENABLED"),
                default=True,
            ),
        )

    def rpc_url_for(self, chain: Chain) -> str | None:
        if chain is Chain.SOLANA:
            urls = self.rpc_urls_for(chain)
            return urls[0] if urls else None
        if chain is Chain.ETHEREUM:
            return self.eth_rpc_url or self._alchemy_url("eth-mainnet")
        if chain is Chain.BASE:
            return self.base_rpc_url or self._alchemy_url("base-mainnet")
        if chain is Chain.BSC:
            return self.bsc_rpc_url or self._alchemy_url("bnb-mainnet")
        return None

    def rpc_urls_for(self, chain: Chain) -> tuple[str, ...]:
        if chain is not Chain.SOLANA:
            url = self.rpc_url_for(chain)
            return (url,) if url else ()

        urls: list[str] = []
        if self.solana_rpc_url:
            urls.append(self.solana_rpc_url)
        urls.extend(f"https://mainnet.helius-rpc.com/?api-key={key}" for key in self.helius_api_keys)
        return tuple(dict.fromkeys(urls))

    def configured_rpc_chains(self) -> tuple[Chain, ...]:
        chains = [chain for chain in Chain if self.rpc_url_for(chain)]
        return tuple(chains)

    def _alchemy_url(self, network: str) -> str | None:
        if not self.alchemy_api_key:
            return None
        return f"https://{network}.g.alchemy.com/v2/{self.alchemy_api_key}"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _split_keys(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _topic_ids_from_env(env: Mapping[str, str]) -> dict[str, int]:
    topic_ids: dict[str, int] = {}
    for key, value in env.items():
        if not key.startswith("TELEGRAM_") or not key.endswith("_TOPIC_ID"):
            continue
        stripped = value.strip()
        if not stripped or not stripped.lstrip("-").isdigit():
            continue
        topic_ids[key] = int(stripped)
    return topic_ids


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
