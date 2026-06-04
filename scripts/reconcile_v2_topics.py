"""Create and verify V2 Telegram forum topics from a VPS .env file.

This script intentionally prints only env keys and counts. It does not print
bot tokens, chat IDs, or topic IDs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ENV_PATH = Path(os.environ.get("TRENCH_V2_ENV", "/opt/trench-tool-v2/.env"))
SHARED_ENV_PATH = Path(os.environ.get("TRENCH_V1_ENV", "/opt/trench-tool/backend/.env"))


ALIASES = {
    "TELEGRAM_SOL_DORMANTS_TOPIC_ID": "TELEGRAM_DORMANTS_TOPIC_ID",
    "TELEGRAM_SOL_FRESHIES_TOPIC_ID": "TELEGRAM_FRESHIES_TOPIC_ID",
    "TELEGRAM_SOL_MIGRATIONS_TRACKER_TOPIC_ID": "TELEGRAM_LATE_MIGRATION_TOPIC_ID",
}

SHARED_TOPIC_KEYS = {
    "TELEGRAM_BEST_SIGNALS_TOPIC_ID",
    "TELEGRAM_BUNDLES_TOPIC_ID",
    "TELEGRAM_SNS_TOPIC_ID",
    "TELEGRAM_STREAMFLOW_TOPIC_ID",
    "TELEGRAM_DEV_HELD_TOPIC_ID",
    "TELEGRAM_GOOD_CREATOR_TOPIC_ID",
    "TELEGRAM_SOCIALS_TOPIC_ID",
    "TELEGRAM_STRONG_LAUNCH_TOPIC_ID",
}

TELEGRAM_TOPIC_COLORS = {
    "blue": 0x6FB9F0,
    "yellow": 0xFFD67E,
    "violet": 0xCB86DB,
    "green": 0x8EEE98,
    "rose": 0xFF93B2,
    "red": 0xFB6F5F,
}


@dataclass(frozen=True, slots=True)
class TopicSpec:
    title: str
    icon_color: int


WANTED_TOPICS = {
    "TELEGRAM_BEST_SIGNALS_TOPIC_ID": TopicSpec("Best Signals", TELEGRAM_TOPIC_COLORS["red"]),
    "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID": TopicSpec("Best Wallets Week", TELEGRAM_TOPIC_COLORS["green"]),
    "TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID": TopicSpec("Best Wallets Month", TELEGRAM_TOPIC_COLORS["violet"]),
    "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID": TopicSpec("Best Wallets Year", TELEGRAM_TOPIC_COLORS["yellow"]),
    "TELEGRAM_BUNDLES_TOPIC_ID": TopicSpec("Bundles (SOL)", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_SNS_TOPIC_ID": TopicSpec("SNS Tracker", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_STREAMFLOW_TOPIC_ID": TopicSpec("Streamflow locks", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_DEV_HELD_TOPIC_ID": TopicSpec("DEV Held", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_GOOD_CREATOR_TOPIC_ID": TopicSpec("Good Token Creator", TELEGRAM_TOPIC_COLORS["green"]),
    "TELEGRAM_SOCIALS_TOPIC_ID": TopicSpec("Socials check", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_STRONG_LAUNCH_TOPIC_ID": TopicSpec("Strong launches", TELEGRAM_TOPIC_COLORS["green"]),
    "TELEGRAM_ETH_FRESHIES_TOPIC_ID": TopicSpec("ETH Freshies", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID": TopicSpec("ETH Big Freshies", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID": TopicSpec("ETH Low MC Freshies", TELEGRAM_TOPIC_COLORS["blue"]),
    "TELEGRAM_BASE_FRESHIES_TOPIC_ID": TopicSpec("Base Freshies", TELEGRAM_TOPIC_COLORS["violet"]),
    "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": TopicSpec("Base Low MC Freshies", TELEGRAM_TOPIC_COLORS["violet"]),
    "TELEGRAM_BASE_DEPLOYS_TOPIC_ID": TopicSpec("Base Deploys", TELEGRAM_TOPIC_COLORS["violet"]),
    "TELEGRAM_BNB_FRESHIES_TOPIC_ID": TopicSpec("BNB Freshies", TELEGRAM_TOPIC_COLORS["yellow"]),
    "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID": TopicSpec("BNB Big Freshies", TELEGRAM_TOPIC_COLORS["yellow"]),
    "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID": TopicSpec("BNB Low MC Freshies", TELEGRAM_TOPIC_COLORS["yellow"]),
}


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def write_env(path: Path, original_lines: list[str], updates: dict[str, str]) -> None:
    seen: set[str] = set()
    output: list[str] = []
    for line in original_lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0]
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line)
    for key in sorted(set(updates) - seen):
        output.append(f"{key}={updates[key]}")
    path.write_text("\n".join(output) + "\n")
    os.chmod(path, 0o600)


class TelegramClient:
    def __init__(self, bot_token: str):
        self.base_url = f"https://api.telegram.org/bot{bot_token}/"

    def request(self, method: str, payload: dict[str, object], retries: int = 6) -> dict:
        data = urllib.parse.urlencode(payload).encode()
        for _ in range(retries):
            req = urllib.request.Request(self.base_url + method, data=data)
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    body = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode(errors="replace")
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError as json_exc:
                    raise RuntimeError(raw) from json_exc
            if body.get("ok"):
                return body["result"]
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if retry_after:
                time.sleep(float(retry_after) + 2)
                continue
            raise RuntimeError(body.get("description") or str(body))
        raise RuntimeError(f"{method} exhausted retries")


def active_topic_id(env: dict[str, str], updates: dict[str, str], key: str) -> str | None:
    value = updates.get(key) or env.get(key, "")
    value = value.strip()
    return value if value and value != "0" else None


def main() -> None:
    original = ENV_PATH.read_text()
    lines = original.splitlines()
    env = parse_env(original)
    bot_token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_GROUP_ID")
    if not bot_token or not chat_id:
        raise SystemExit("missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    updates: dict[str, str] = {}
    for new_key, old_key in ALIASES.items():
        if active_topic_id(env, updates, new_key):
            continue
        old_value = active_topic_id(env, updates, old_key)
        if old_value:
            updates[new_key] = old_value

    telegram = TelegramClient(bot_token)
    created: list[str] = []
    for key, spec in WANTED_TOPICS.items():
        if active_topic_id(env, updates, key):
            continue
        topic = telegram.request(
            "createForumTopic",
            {"chat_id": chat_id, "name": spec.title, "icon_color": spec.icon_color},
        )
        updates[key] = str(topic["message_thread_id"])
        created.append(key)
        time.sleep(1.2)

    verified: set[str] = set()
    for key in sorted(set(ALIASES) | set(WANTED_TOPICS)):
        thread_id = active_topic_id(env, updates, key)
        if not thread_id:
            continue
        message = telegram.request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "message_thread_id": thread_id,
                "text": "V2 topic wiring check",
                "disable_notification": "true",
            },
        )
        telegram.request("deleteMessage", {"chat_id": chat_id, "message_id": message["message_id"]})
        verified.add(key)
        time.sleep(0.4)

    if updates:
        backup = ENV_PATH.with_suffix(".env.topic-backup-" + time.strftime("%Y%m%d%H%M%S"))
        backup.write_text(original)
        write_env(ENV_PATH, lines, updates)
        shared_updates = {key: value for key, value in updates.items() if key in SHARED_TOPIC_KEYS}
        if shared_updates and SHARED_ENV_PATH.exists():
            shared_original = SHARED_ENV_PATH.read_text()
            shared_backup = SHARED_ENV_PATH.with_suffix(".env.topic-backup-" + time.strftime("%Y%m%d%H%M%S"))
            shared_backup.write_text(shared_original)
            write_env(
                SHARED_ENV_PATH,
                shared_original.splitlines(),
                shared_updates,
            )

    print(f"aliases_or_created={len(updates)}")
    print(f"created={len(created)}")
    for key in created:
        print(f"created_key={key}")
    print(f"verified={len(verified)}")


if __name__ == "__main__":
    main()
