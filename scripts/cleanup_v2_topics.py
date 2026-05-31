"""Delete Telegram forum topics that do not have live producers."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ENV_PATHS = [
    Path("/opt/trench-tool-v2/.env"),
    Path("/opt/trench-tool/backend/.env"),
]


KEEP_TOPIC_KEYS = {
    "TELEGRAM_BEST_SIGNALS_TOPIC_ID",
    # V1 SOL producers that are active on the live bot.
    "TELEGRAM_FRESHIES_TOPIC_ID",
    "TELEGRAM_SOL_FRESHIES_TOPIC_ID",
    "TELEGRAM_DORMANTS_TOPIC_ID",
    "TELEGRAM_SOL_DORMANTS_TOPIC_ID",
    "TELEGRAM_LATE_MIGRATION_TOPIC_ID",
    "TELEGRAM_SOL_MIGRATIONS_TRACKER_TOPIC_ID",
    "TELEGRAM_PATTERNS_TOPIC_ID",
    "TELEGRAM_SOL_PATTERNS_TOPIC_ID",
    "TELEGRAM_WIZARD_TOPIC_ID",
    "TELEGRAM_SOL_WIZARD_TOPIC_ID",
    "TELEGRAM_BUNDLES_TOPIC_ID",
    "TELEGRAM_SNS_TOPIC_ID",
    "TELEGRAM_VANISH_TOPIC_ID",
    "TELEGRAM_STREAMFLOW_TOPIC_ID",
    "TELEGRAM_DEV_HELD_TOPIC_ID",
    "TELEGRAM_GOOD_CREATOR_TOPIC_ID",
    "TELEGRAM_SOCIALS_TOPIC_ID",
    "TELEGRAM_STRONG_LAUNCH_TOPIC_ID",
    "TELEGRAM_STRONGFLOOR_TOPIC_ID",
    # V2 EVM producers that are active on the side-by-side worker.
    "TELEGRAM_ETH_FRESHIES_TOPIC_ID",
    "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID",
    "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID",
    "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
    "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
    "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
    "TELEGRAM_BNB_FRESHIES_TOPIC_ID",
    "TELEGRAM_BNB_BIG_FRESHIES_TOPIC_ID",
    "TELEGRAM_BNB_LOW_MC_FRESHIES_TOPIC_ID",
    "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID",
    "TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID",
    "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID",
}


def parse_env(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value.strip().strip('"').strip("'")
    return env


def telegram_request(bot_token: str, method: str, payload: dict[str, object]) -> dict:
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


def all_topic_keys(env: dict[str, str]) -> set[str]:
    return {key for key in env if key.startswith("TELEGRAM_") and key.endswith("_TOPIC_ID")}


def removable_topic_keys(env: dict[str, str]) -> set[str]:
    return all_topic_keys(env) - KEEP_TOPIC_KEYS


def zero_removed_keys(path: Path, keys: set[str]) -> int:
    original = path.read_text()
    lines = original.splitlines()
    output: list[str] = []
    changed = 0
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0]
            if key in keys:
                output.append(f"{key}=0")
                changed += 1
                continue
        output.append(line)
    if changed:
        backup = path.with_suffix(".env.cleanup-backup-" + time.strftime("%Y%m%d%H%M%S"))
        backup.write_text(original)
        path.write_text("\n".join(output) + "\n")
        os.chmod(path, 0o600)
    return changed


def main() -> None:
    v2_env = parse_env(ENV_PATHS[0].read_text())
    bot_token = v2_env.get("TELEGRAM_BOT_TOKEN")
    chat_id = v2_env.get("TELEGRAM_CHAT_ID") or v2_env.get("TELEGRAM_GROUP_ID")
    if not bot_token or not chat_id:
        raise SystemExit("missing Telegram token/chat id")

    env_by_path: dict[Path, dict[str, str]] = {}
    remove_topic_keys = set()
    for path in ENV_PATHS:
        if path.exists():
            env_by_path[path] = parse_env(path.read_text())
            remove_topic_keys.update(removable_topic_keys(env_by_path[path]))

    keep_thread_ids = {
        value
        for env in env_by_path.values()
        for key, value in env.items()
        if key in KEEP_TOPIC_KEYS and value and value != "0" and value.strip().lstrip("-").isdigit()
    }

    deleted = 0
    already_gone = 0
    attempted_thread_ids: set[str] = set()
    for env in env_by_path.values():
        for key in sorted(remove_topic_keys):
            value = env.get(key, "").strip()
            if not value or value == "0" or not value.lstrip("-").isdigit():
                continue
            if value in keep_thread_ids or value in attempted_thread_ids:
                continue
            attempted_thread_ids.add(value)
            result = telegram_request(
                bot_token,
                "deleteForumTopic",
                {"chat_id": chat_id, "message_thread_id": int(value)},
            )
            if result.get("ok"):
                deleted += 1
                continue
            description = str(result.get("description", "")).lower()
            if "message thread not found" in description:
                already_gone += 1
                continue
            print(f"delete_failed={key}:{result.get('description')}")

    zeroed = 0
    for path in ENV_PATHS:
        if path.exists():
            zeroed += zero_removed_keys(path, remove_topic_keys)

    print(f"deleted={deleted}")
    print(f"already_gone={already_gone}")
    print(f"zeroed={zeroed}")
    print(f"kept={len(KEEP_TOPIC_KEYS)}")


if __name__ == "__main__":
    main()
