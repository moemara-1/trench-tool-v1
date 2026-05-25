"""Telegram sending helpers for V2 alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class TelegramSender(Protocol):
    async def send(self, topic_id: int, text: str) -> bool:
        """Send a message to a Telegram forum topic."""


@dataclass(slots=True)
class BotApiTelegramSender:
    bot_token: str
    chat_id: str
    timeout_seconds: float = 15.0

    async def send(self, topic_id: int, text: str) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "message_thread_id": topic_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        return bool(data.get("ok"))
