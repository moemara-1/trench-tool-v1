import pytest

from trench_v2.core.models import Chain
from trench_v2.providers.evm import (
    ALCHEMY_TRANSFER_CATEGORIES,
    APPROVAL_TOPIC,
    PAIR_CREATED_TOPIC,
    POOL_CREATED_TOPIC,
    AlchemyTransfersClient,
    EtherscanV2Client,
    decode_v2_pair_created,
    decode_v3_pool_created,
)


class FakeGetClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get_json(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, params or {}))
        return self.response


class FakePostClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post_json(self, url: str, payload: dict):
        self.calls.append((url, payload))
        if isinstance(self.response, list):
            return self.response[len(self.calls) - 1]
        return self.response


@pytest.mark.asyncio
async def test_etherscan_v2_client_builds_log_request_and_normalizes_logs():
    client = FakeGetClient(
        {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "address": "0xFactory",
                    "topics": [PAIR_CREATED_TOPIC, _topic_address("0x" + "11" * 20)],
                    "data": "0x",
                    "blockNumber": "0x10",
                    "timeStamp": "0x65",
                    "logIndex": "0x2",
                    "transactionHash": "0xtx",
                }
            ],
        }
    )
    provider = EtherscanV2Client(api_key="etherscan", client=client)

    logs = await provider.get_logs(
        chain=Chain.BASE,
        address="0xFactory",
        topic0=PAIR_CREATED_TOPIC,
        from_block=10,
        to_block=20,
        page=2,
        offset=500,
    )

    assert len(logs) == 1
    assert logs[0].chain is Chain.BASE
    assert logs[0].block_number == 16
    assert logs[0].log_index == 2
    assert logs[0].tx_hash == "0xtx"
    assert client.calls[0][0] == "https://api.etherscan.io/v2/api"
    assert client.calls[0][1] == {
        "apikey": "etherscan",
        "chainid": "8453",
        "module": "logs",
        "action": "getLogs",
        "address": "0xFactory",
        "fromBlock": "10",
        "toBlock": "20",
        "topic0": PAIR_CREATED_TOPIC,
        "page": "2",
        "offset": "500",
    }


@pytest.mark.asyncio
async def test_etherscan_v2_client_allows_topic_only_log_queries():
    client = FakeGetClient({"status": "1", "message": "OK", "result": []})
    provider = EtherscanV2Client(api_key="etherscan", client=client)

    await provider.get_logs(
        chain=Chain.ETHEREUM,
        address=None,
        topic0=APPROVAL_TOPIC,
        from_block=1,
        to_block=2,
    )

    assert "address" not in client.calls[0][1]
    assert client.calls[0][1]["topic0"] == APPROVAL_TOPIC


def test_decode_v2_pair_created_extracts_tokens_and_pair_address():
    pair = "0x" + "33" * 20
    log = _log(
        topics=[
            PAIR_CREATED_TOPIC,
            _topic_address("0x" + "11" * 20),
            _topic_address("0x" + "22" * 20),
        ],
        data="0x" + ("0" * 24 + pair[2:]) + ("0" * 63 + "1"),
    )

    event = decode_v2_pair_created(log)

    assert event is not None
    assert event.token0 == "0x" + "11" * 20
    assert event.token1 == "0x" + "22" * 20
    assert event.pool_address == pair
    assert event.pool_type == "V2"


def test_decode_v3_pool_created_extracts_tokens_fee_and_pool_address():
    pool = "0x" + "44" * 20
    log = _log(
        topics=[
            POOL_CREATED_TOPIC,
            _topic_address("0x" + "11" * 20),
            _topic_address("0x" + "22" * 20),
            "0x" + ("0" * 63 + "5"),
        ],
        data="0x" + ("0" * 63 + "1") + ("0" * 24 + pool[2:]),
    )

    event = decode_v3_pool_created(log)

    assert event is not None
    assert event.token0 == "0x" + "11" * 20
    assert event.token1 == "0x" + "22" * 20
    assert event.pool_address == pool
    assert event.pool_type == "V3"


@pytest.mark.asyncio
async def test_alchemy_transfers_client_builds_wallet_history_request():
    transfer_payload = {
        "result": {
            "transfers": [
                {
                    "from": "0xfrom",
                    "to": "0xto",
                    "asset": "TEST",
                    "value": 3.5,
                    "hash": "0xhash",
                    "rawContract": {"address": "0xtoken"},
                    "blockNum": "0x20",
                    "category": "erc20",
                    "metadata": {"blockTimestamp": "2026-05-24T12:00:00.000Z"},
                }
            ]
        }
    }
    client = FakePostClient([transfer_payload, {"result": {"transfers": []}}])
    provider = AlchemyTransfersClient(rpc_url="https://alchemy.example", client=client)

    transfers = await provider.transfers_for_wallet(Chain.ETHEREUM, "0xwallet", max_count=50)

    assert transfers[0].asset == "TEST"
    assert transfers[0].value == 3.5
    assert transfers[0].token_address == "0xtoken"
    assert transfers[0].block_number == 32
    assert transfers[0].timestamp is not None
    assert [call[0] for call in client.calls] == ["https://alchemy.example", "https://alchemy.example"]
    assert client.calls[0][1]["method"] == "alchemy_getAssetTransfers"
    assert client.calls[1][1]["method"] == "alchemy_getAssetTransfers"
    params = client.calls[0][1]["params"][0]
    assert params["fromAddress"] == "0xwallet"
    assert "toAddress" not in params
    assert params["category"] == ALCHEMY_TRANSFER_CATEGORIES
    assert params["withMetadata"] is True
    assert params["maxCount"] == "0x32"
    assert client.calls[1][1]["params"][0]["toAddress"] == "0xwallet"


def test_evm_event_topics_are_pinned_to_protocol_signatures():
    assert PAIR_CREATED_TOPIC == "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    assert POOL_CREATED_TOPIC == "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
    assert APPROVAL_TOPIC == "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"


def _topic_address(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def _log(topics: list[str], data: str):
    from trench_v2.providers.evm import EvmLogEvent

    return EvmLogEvent(
        chain=Chain.BSC,
        address="0xfactory",
        block_number=1,
        tx_hash="0xtx",
        topics=topics,
        data=data,
        log_index=0,
        timestamp=1,
    )
