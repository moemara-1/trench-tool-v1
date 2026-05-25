"""Probe specific deleted Telegram topics and delete any that still exist."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CURRENT_ENV = Path("/opt/trench-tool-v2/.env")
BACKUP_ENV = Path("/opt/trench-tool-v2/.env.env.cleanup-backup-20260524114255")


DELETE_KEYS = {
    "TELEGRAM_SOL_LOW_MC_FRESHIES_TOPIC_ID": "SOL Low MC Big Freshies",
    "TELEGRAM_SOL_BIG_DORMANTS_TOPIC_ID": "Big Dormants (SOL)",
    "TELEGRAM_SOL_SEMI_DORMANTS_SELLS_TOPIC_ID": "Semi-Dormants Sells (SOL)",
    "TELEGRAM_SOL_SEMI_DORMANTS_TOPIC_ID": "Semi-Dormants (SOL)",
    "TELEGRAM_SOL_FRESHIES_SELLS_TOPIC_ID": "Freshies Sells (SOL)",
    "TELEGRAM_SOL_SIMULATE_TOPIC_ID": "SOL Simulate",
    "TELEGRAM_SOL_TRACK_TOPIC_ID": "SOL Track",
    "TELEGRAM_SOL_SCAN_TOPIC_ID": "SOL Scan",
    "TELEGRAM_BNB_BUNDLES_TOPIC_ID": "BNB Bundles",
    "TELEGRAM_BNB_SEMI_DORMANTS_TOPIC_ID": "BNB Semi-Dormants",
    "TELEGRAM_BNB_DORMANTS_TOPIC_ID": "BNB Dormants",
    "TELEGRAM_BNB_ANALYZE_TOPIC_ID": "BNB Analyze",
    "TELEGRAM_BASE_BUNDLES_TOPIC_ID": "Base Bundles",
    "TELEGRAM_BASE_ENS_BUYS_TOPIC_ID": "Base ENS Buys",
    "TELEGRAM_BUNDLES_TOPIC_ID": "Bundles(SOL)",
    "TELEGRAM_SOL_BUNDLES_TOPIC_ID": "Bundles(SOL)",
    "TELEGRAM_PATTERNS_TOPIC_ID": "Patterns (SOL)",
    "TELEGRAM_SOL_PATTERNS_TOPIC_ID": "Patterns (SOL)",
    "TELEGRAM_WIZARD_TOPIC_ID": "Freshies Wizard",
    "TELEGRAM_SOL_WIZARD_TOPIC_ID": "Freshies Wizard",
    "TELEGRAM_SNS_TOPIC_ID": "SNS Tracker",
    "TELEGRAM_SOL_SNS_TOPIC_ID": "SNS Tracker",
    "TELEGRAM_SOCIALS_TOPIC_ID": "Socials check",
    "TELEGRAM_SOL_SOCIALS_TOPIC_ID": "Socials check",
    "TELEGRAM_DEV_HELD_TOPIC_ID": "DEV Held",
    "TELEGRAM_SOL_DEV_HELD_TOPIC_ID": "DEV Held",
    "TELEGRAM_GOOD_CREATOR_TOPIC_ID": "Good Token creators",
    "TELEGRAM_SOL_GOOD_CREATOR_TOPIC_ID": "Good Token creators",
    "TELEGRAM_STRONG_LAUNCH_TOPIC_ID": "Strong launches",
    "TELEGRAM_SOL_STRONG_LAUNCH_TOPIC_ID": "Strong launches",
    "TELEGRAM_STRONGFLOOR_TOPIC_ID": "Strong floor",
    "TELEGRAM_SOL_STRONGFLOOR_TOPIC_ID": "Strong floor",
    "TELEGRAM_STREAMFLOW_TOPIC_ID": "Streamflow locks",
    "TELEGRAM_SOL_STREAMFLOW_TOPIC_ID": "Streamflow locks",
    "TELEGRAM_VANISH_TOPIC_ID": "Vanish Buys(SOL)",
}


KEEP_KEYS = {
    "TELEGRAM_BNB_FRESHIES_TOPIC_ID": "BNB Freshies",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    text = path.read_text() if path.exists() else ""
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def request(bot_token: str, method: str, payload: dict[str, object]) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{bot_token}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "description": raw}


def topic_value(current: dict[str, str], backup: dict[str, str], key: str) -> str | None:
    for source in (current, backup):
        value = source.get(key)
        if value and value != "0" and value.lstrip("-").isdigit():
            return value
    return None


def probe(bot_token: str, chat_id: str, thread_id: str) -> tuple[bool, str]:
    result = request(
        bot_token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "message_thread_id": int(thread_id),
            "text": "topic cleanup verification",
            "disable_notification": "true",
        },
    )
    if not result.get("ok"):
        return False, str(result.get("description", "unknown"))
    message_id = result["result"]["message_id"]
    request(bot_token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    return True, "accepts_messages"


def main() -> None:
    current = parse_env(CURRENT_ENV)
    backup = parse_env(BACKUP_ENV)
    bot_token = current.get("TELEGRAM_BOT_TOKEN") or backup.get("TELEGRAM_BOT_TOKEN")
    chat_id = current.get("TELEGRAM_CHAT_ID") or backup.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise SystemExit("missing Telegram token/chat id")

    deleted_now = 0
    already_dead = 0
    still_kept = 0
    missing_id = 0
    for key, title in DELETE_KEYS.items():
        value = topic_value(current, backup, key)
        if not value:
            print(f"missing_id={title}")
            missing_id += 1
            continue
        alive, detail = probe(bot_token, chat_id, value)
        if alive:
            deleted = request(
                bot_token,
                "deleteForumTopic",
                {"chat_id": chat_id, "message_thread_id": int(value)},
            )
            if deleted.get("ok"):
                print(f"deleted_now={title}")
                deleted_now += 1
            else:
                print(f"delete_failed={title}:{deleted.get('description')}")
        else:
            print(f"already_dead={title}:{detail}")
            already_dead += 1
        time.sleep(0.2)

    for key, title in KEEP_KEYS.items():
        value = topic_value(current, backup, key)
        if not value:
            print(f"keep_missing={title}")
            continue
        alive, detail = probe(bot_token, chat_id, value)
        print(f"keep_alive={title}:{alive}:{detail}")
        still_kept += int(alive)

    print(f"summary deleted_now={deleted_now} already_dead={already_dead} missing_id={missing_id} kept_alive={still_kept}")


if __name__ == "__main__":
    main()
