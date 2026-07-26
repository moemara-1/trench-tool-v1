import pytest

from alerts import telegram_bot
from alerts.telegram_bot import TelegramAlertBot
from best_signals import BestSignalRouter
from quality_budget import is_signal_alert_message, score_v1_alert_message


DORMANT_MESSAGE = """SOL Dormants
$STONKS Stonks Leader 0.51 $48.1k
<code>9ttcxL8Ztz8nv3tQiS9Lu6KpjA2VofNrRXx7nw27z62C</code>
LS: 113d | CA: 708d
<a href="https://axiom.trade/meme/pair?chain=sol">AX</a> | <a href="https://dexscreener.com/solana/token">XX</a>"""


FRESHIES_WIZARD_MESSAGE = """[4] 7 Fresh buys 5 minutes since last update
$ETHERE Etheway 61d 17.7M
HmBdm8vbisABUjkxms6ZUnoaXbfwFM6ymxShWfAENaoi"""


STRONGFLOOR_MESSAGE = """SOL Strongfloor
$PTAI Paladin Trump AI | Strength: 48/100
Floor: $0.000816 | Bounces: 2 | Time: 9h
MC: 977.9k
2SAt9qF6YjMBz9tb1U9jAYNBBVx5jqWQ7KRXDqD2pump"""


ELITE_STRONGFLOOR_MESSAGE = """SOL Strongfloor
$WHALE Whale Token | Strength: 99/100
Floor: $0.000816 | Bounces: 4 | Time: 9h
MC: 977.9k
<code>9ttcxL8Ztz8nv3tQiS9Lu6KpjA2VofNrRXx7nw27z62C</code>
<a href="https://dexscreener.com/solana/token">XX</a>"""


class FakeTelegramResult:
    def __init__(self, message_id: int):
        self.message_id = message_id


class FakeTelegramApi:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return FakeTelegramResult(len(self.calls))


@pytest.mark.parametrize("message", [DORMANT_MESSAGE, FRESHIES_WIZARD_MESSAGE, STRONGFLOOR_MESSAGE])
def test_v1_signal_messages_score_above_default_floor(message):
    assert is_signal_alert_message(message) is True
    assert score_v1_alert_message(message) >= 70


@pytest.mark.asyncio
async def test_v1_send_alert_blocks_signal_without_topic():
    bot = TelegramAlertBot(token="fake-token", chat_id="-100123")

    result = await bot.send_alert(STRONGFLOOR_MESSAGE)

    assert result is None


@pytest.mark.asyncio
async def test_v1_send_alert_blocks_signal_routed_to_feedback(monkeypatch):
    monkeypatch.setattr(telegram_bot.settings, "telegram_feedback_topic_id", 777, raising=False)
    bot = TelegramAlertBot(token="fake-token", chat_id="-100123")

    result = await bot.send_alert(DORMANT_MESSAGE, topic_id=777)

    assert result is None


@pytest.mark.asyncio
async def test_v1_send_alert_keeps_unverified_v1_signal_out_of_best_signals(monkeypatch):
    monkeypatch.setattr(telegram_bot.settings, "telegram_best_signals_topic_id", 999, raising=False)
    monkeypatch.setattr(telegram_bot.settings, "best_signals_daily_cap", 7, raising=False)
    monkeypatch.setattr(telegram_bot.settings, "best_signals_min_score", 95, raising=False)
    monkeypatch.setattr(
        telegram_bot,
        "_best_signal_router",
        BestSignalRouter(daily_cap=7, min_score=95),
        raising=False,
    )
    bot = TelegramAlertBot(token="fake-token", chat_id="-100123")
    fake_api = FakeTelegramApi()
    bot._bot = fake_api

    result = await bot.send_alert(ELITE_STRONGFLOOR_MESSAGE, topic_id=3)

    assert result == 1
    assert [call["message_thread_id"] for call in fake_api.calls] == [3]
