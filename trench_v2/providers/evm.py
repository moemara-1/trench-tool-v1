"""EVM explorer/RPC primitives for launches, approvals, and wallet history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from trench_v2.core.models import Chain
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ALCHEMY_TRANSFER_CATEGORIES = ["external", "erc20", "erc721", "erc1155", "specialnft"]

_CHAIN_IDS = {
    Chain.ETHEREUM: "1",
    Chain.BASE: "8453",
    Chain.BSC: "56",
}


class EtherscanJsonClient(Protocol):
    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict | list:
        """Return JSON from Etherscan V2."""


class RpcJsonClient(Protocol):
    async def post_json(self, url: str, payload: dict) -> dict:
        """Return JSON from a JSON-RPC endpoint."""


@dataclass(frozen=True, slots=True)
class EvmLogEvent:
    chain: Chain
    address: str
    block_number: int
    tx_hash: str
    topics: list[str]
    data: str
    log_index: int
    timestamp: int | None = None


@dataclass(frozen=True, slots=True)
class LaunchPoolEvent:
    chain: Chain
    factory_address: str
    token0: str
    token1: str
    pool_address: str
    pool_type: str
    tx_hash: str
    block_number: int


@dataclass(frozen=True, slots=True)
class WalletTransfer:
    chain: Chain
    from_address: str | None
    to_address: str | None
    asset: str | None
    value: float | None
    token_address: str | None
    tx_hash: str
    block_number: int | None
    category: str | None
    timestamp: datetime | None = None


class EtherscanV2Client:
    """Small Etherscan V2 wrapper for log backfills."""

    def __init__(self, api_key: str, client: EtherscanJsonClient | None = None):
        self.api_key = api_key
        self.client = client or AsyncJsonClient("etherscan-v2")

    async def get_logs(
        self,
        *,
        chain: Chain,
        address: str | None,
        from_block: int,
        to_block: int,
        topic0: str | None = None,
        page: int = 1,
        offset: int = 1000,
    ) -> list[EvmLogEvent]:
        chain_id = _chain_id(chain)
        params = {
            "apikey": self.api_key,
            "chainid": chain_id,
            "module": "logs",
            "action": "getLogs",
            "fromBlock": str(from_block),
            "toBlock": str(to_block),
            "page": str(page),
            "offset": str(offset),
        }
        if address:
            params["address"] = address
        if topic0:
            params["topic0"] = topic0

        try:
            data = await self.client.get_json("https://api.etherscan.io/v2/api", params=params)
        except ProviderRateLimitError:
            raise

        if not isinstance(data, dict):
            return []
        result = data.get("result")
        if not isinstance(result, list):
            return []
        return [_log_from_json(chain, item) for item in result if isinstance(item, dict)]


class AlchemyTransfersClient:
    """Alchemy Transfers API wrapper for wallet-history primitives."""

    def __init__(self, rpc_url: str, client: RpcJsonClient | None = None):
        self.rpc_url = rpc_url
        self.client = client or AsyncJsonClient("alchemy-transfers")

    async def transfers_for_wallet(
        self,
        chain: Chain,
        wallet: str,
        *,
        max_count: int = 100,
    ) -> list[WalletTransfer]:
        outgoing = await self._fetch_direction(chain, "fromAddress", wallet, max_count=max_count)
        incoming = await self._fetch_direction(chain, "toAddress", wallet, max_count=max_count)
        seen: set[str] = set()
        transfers: list[WalletTransfer] = []
        for transfer in [*outgoing, *incoming]:
            key = f"{transfer.tx_hash}:{transfer.from_address}:{transfer.to_address}:{transfer.token_address}"
            if key in seen:
                continue
            seen.add(key)
            transfers.append(transfer)
        return transfers

    async def _fetch_direction(
        self,
        chain: Chain,
        address_key: str,
        wallet: str,
        *,
        max_count: int,
    ) -> list[WalletTransfer]:
        params = {
            "fromBlock": "0x0",
            "toBlock": "latest",
            address_key: wallet,
            "category": ALCHEMY_TRANSFER_CATEGORIES,
            "withMetadata": True,
            "excludeZeroValue": False,
            "maxCount": hex(max_count),
            "order": "desc",
        }
        data = await self.client.post_json(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [params],
            },
        )
        result = data.get("result") if isinstance(data, dict) else None
        raw_transfers = result.get("transfers") if isinstance(result, dict) else None
        if not isinstance(raw_transfers, list):
            return []
        return [_transfer_from_json(chain, item) for item in raw_transfers if isinstance(item, dict)]


def decode_v2_pair_created(log: EvmLogEvent) -> LaunchPoolEvent | None:
    if not log.topics or log.topics[0].lower() != PAIR_CREATED_TOPIC:
        return None
    if len(log.topics) < 3:
        return None
    pair_address = _address_from_data_word(log.data, 0)
    if pair_address is None:
        return None
    return LaunchPoolEvent(
        chain=log.chain,
        factory_address=log.address,
        token0=_address_from_topic(log.topics[1]),
        token1=_address_from_topic(log.topics[2]),
        pool_address=pair_address,
        pool_type="V2",
        tx_hash=log.tx_hash,
        block_number=log.block_number,
    )


def decode_v3_pool_created(log: EvmLogEvent) -> LaunchPoolEvent | None:
    if not log.topics or log.topics[0].lower() != POOL_CREATED_TOPIC:
        return None
    if len(log.topics) < 4:
        return None
    pool_address = _address_from_data_word(log.data, 1)
    if pool_address is None:
        return None
    return LaunchPoolEvent(
        chain=log.chain,
        factory_address=log.address,
        token0=_address_from_topic(log.topics[1]),
        token1=_address_from_topic(log.topics[2]),
        pool_address=pool_address,
        pool_type="V3",
        tx_hash=log.tx_hash,
        block_number=log.block_number,
    )


def _chain_id(chain: Chain) -> str:
    if chain not in _CHAIN_IDS:
        raise ValueError(f"Etherscan V2 does not support chain {chain.value}")
    return _CHAIN_IDS[chain]


def _log_from_json(chain: Chain, item: dict) -> EvmLogEvent:
    topics = item.get("topics") if isinstance(item.get("topics"), list) else []
    return EvmLogEvent(
        chain=chain,
        address=str(item.get("address") or ""),
        block_number=_int_from_hex_or_decimal(item.get("blockNumber")),
        tx_hash=str(item.get("transactionHash") or ""),
        topics=[str(topic) for topic in topics],
        data=str(item.get("data") or "0x"),
        log_index=_int_from_hex_or_decimal(item.get("logIndex")),
        timestamp=_optional_int_from_hex_or_decimal(item.get("timeStamp")),
    )


def _transfer_from_json(chain: Chain, item: dict) -> WalletTransfer:
    raw_contract = item.get("rawContract") if isinstance(item.get("rawContract"), dict) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return WalletTransfer(
        chain=chain,
        from_address=_str_or_none(item.get("from")),
        to_address=_str_or_none(item.get("to")),
        asset=_str_or_none(item.get("asset")),
        value=_float_or_none(item.get("value")),
        token_address=_str_or_none(raw_contract.get("address")),
        tx_hash=str(item.get("hash") or ""),
        block_number=_optional_int_from_hex_or_decimal(item.get("blockNum")),
        category=_str_or_none(item.get("category")),
        timestamp=_datetime_or_none(metadata.get("blockTimestamp")),
    )


def _address_from_topic(topic: str) -> str:
    normalized = topic.lower()
    return "0x" + normalized[-40:]


def _address_from_data_word(data: str, word_index: int) -> str | None:
    normalized = data[2:] if data.startswith("0x") else data
    start = word_index * 64
    word = normalized[start : start + 64]
    if len(word) != 64:
        return None
    return "0x" + word[-40:].lower()


def _optional_int_from_hex_or_decimal(value: object) -> int | None:
    if value is None:
        return None
    return _int_from_hex_or_decimal(value)


def _int_from_hex_or_decimal(value: object) -> int:
    text = str(value or "0")
    try:
        return int(text, 16) if text.startswith("0x") else int(text)
    except ValueError:
        return 0


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _datetime_or_none(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
