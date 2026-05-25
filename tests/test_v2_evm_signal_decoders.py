from trench_v2.core.models import Chain
from trench_v2.engine.evm_signals import (
    BSC_PANCAKE_V2_FACTORY,
    ETH_UNISWAP_V2_FACTORY,
    ETH_UNISWAP_V3_FACTORY,
    EvmLogQueryPlanner,
    decode_approval_log,
)
from trench_v2.providers.evm import APPROVAL_TOPIC, EvmLogEvent, PAIR_CREATED_TOPIC, POOL_CREATED_TOPIC


def test_log_query_planner_includes_launch_and_approval_queries_for_chain():
    planner = EvmLogQueryPlanner()

    queries = planner.queries_for(Chain.ETHEREUM, from_block=100, to_block=200)

    launch_queries = [query for query in queries if query.feature == "launches_tracker"]
    approval_queries = [query for query in queries if query.feature == "pre_approvals"]
    assert {query.address for query in launch_queries} == {
        ETH_UNISWAP_V2_FACTORY,
        ETH_UNISWAP_V3_FACTORY,
    }
    assert {query.topic0 for query in launch_queries} == {PAIR_CREATED_TOPIC, POOL_CREATED_TOPIC}
    assert approval_queries[0].topic0 == APPROVAL_TOPIC
    assert approval_queries[0].from_block == 100
    assert approval_queries[0].to_block == 200


def test_log_query_planner_uses_pancake_factory_for_bsc_migrations():
    planner = EvmLogQueryPlanner()

    queries = planner.queries_for(Chain.BSC, from_block=1, to_block=2)

    launch_queries = [query for query in queries if query.feature == "launches_tracker"]
    assert len(launch_queries) == 1
    assert launch_queries[0].address == BSC_PANCAKE_V2_FACTORY
    assert launch_queries[0].topic0 == PAIR_CREATED_TOPIC


def test_decode_approval_log_extracts_owner_spender_and_amount():
    owner = "0x" + "11" * 20
    spender = "0x" + "22" * 20
    log = EvmLogEvent(
        chain=Chain.BASE,
        address="0x" + "33" * 20,
        block_number=123,
        tx_hash="0xtx",
        topics=[
            APPROVAL_TOPIC,
            _topic_address(owner),
            _topic_address(spender),
        ],
        data="0x" + ("0" * 63 + "a"),
        log_index=4,
    )

    approval = decode_approval_log(log)

    assert approval is not None
    assert approval.chain is Chain.BASE
    assert approval.token_address == "0x" + "33" * 20
    assert approval.owner == owner
    assert approval.spender == spender
    assert approval.amount == 10
    assert approval.tx_hash == "0xtx"


def _topic_address(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()

