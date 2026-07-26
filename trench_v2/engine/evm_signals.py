"""Decoded EVM signal contracts for launches and pre-approvals."""

from __future__ import annotations

from dataclasses import dataclass

from trench_v2.core.models import Chain
from trench_v2.providers.evm import APPROVAL_TOPIC, PAIR_CREATED_TOPIC, POOL_CREATED_TOPIC, EvmLogEvent


ETH_UNISWAP_V2_FACTORY = "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"
ETH_UNISWAP_V3_FACTORY = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
BASE_UNISWAP_V3_FACTORY = "0x33128a8fc17869897dce68ed026d694621f6fdfd"
BSC_PANCAKE_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
# Verified against live PairCreated/PoolCreated logs and DexScreener-indexed pools.
ROBINHOOD_UNISWAP_V2_FACTORY = "0x8bceaa40b9acdfaedf85adf4ff01f5ad6517937f"
ROBINHOOD_UNISWAP_V3_FACTORY = "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"


@dataclass(frozen=True, slots=True)
class EvmLogQuery:
    chain: Chain
    feature: str
    address: str | None
    topic0: str
    from_block: int
    to_block: int


@dataclass(frozen=True, slots=True)
class ApprovalEvent:
    chain: Chain
    token_address: str
    owner: str
    spender: str
    amount: int
    tx_hash: str
    block_number: int
    log_index: int


class EvmLogQueryPlanner:
    """Build provider-neutral log queries for EVM features."""

    _LAUNCH_FACTORIES = {
        Chain.ETHEREUM: [
            (ETH_UNISWAP_V2_FACTORY, PAIR_CREATED_TOPIC),
            (ETH_UNISWAP_V3_FACTORY, POOL_CREATED_TOPIC),
        ],
        Chain.BASE: [
            (BASE_UNISWAP_V3_FACTORY, POOL_CREATED_TOPIC),
        ],
        Chain.BSC: [
            (BSC_PANCAKE_V2_FACTORY, PAIR_CREATED_TOPIC),
        ],
        Chain.ROBINHOOD: [
            (ROBINHOOD_UNISWAP_V2_FACTORY, PAIR_CREATED_TOPIC),
            (ROBINHOOD_UNISWAP_V3_FACTORY, POOL_CREATED_TOPIC),
        ],
    }

    def queries_for(self, chain: Chain, *, from_block: int, to_block: int) -> list[EvmLogQuery]:
        queries: list[EvmLogQuery] = []
        for factory_address, topic in self._LAUNCH_FACTORIES.get(chain, []):
            queries.append(
                EvmLogQuery(
                    chain=chain,
                    feature="launches_tracker",
                    address=factory_address,
                    topic0=topic,
                    from_block=from_block,
                    to_block=to_block,
                )
            )

        if chain in {Chain.ETHEREUM, Chain.BASE, Chain.BSC, Chain.ROBINHOOD}:
            queries.append(
                EvmLogQuery(
                    chain=chain,
                    feature="pre_approvals",
                    address=None,
                    topic0=APPROVAL_TOPIC,
                    from_block=from_block,
                    to_block=to_block,
                )
            )
        return queries


def decode_approval_log(log: EvmLogEvent) -> ApprovalEvent | None:
    if not log.topics or log.topics[0].lower() != APPROVAL_TOPIC:
        return None
    if len(log.topics) < 3:
        return None
    amount = _int_from_hex(log.data)
    return ApprovalEvent(
        chain=log.chain,
        token_address=log.address.lower(),
        owner=_address_from_topic(log.topics[1]),
        spender=_address_from_topic(log.topics[2]),
        amount=amount,
        tx_hash=log.tx_hash,
        block_number=log.block_number,
        log_index=log.log_index,
    )


def _address_from_topic(topic: str) -> str:
    normalized = topic.lower()
    return "0x" + normalized[-40:]


def _int_from_hex(value: str) -> int:
    text = value[2:] if value.startswith("0x") else value
    if not text:
        return 0
    try:
        return int(text, 16)
    except ValueError:
        return 0

