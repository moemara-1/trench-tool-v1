"""Append-only journal for V2 source alerts.

This captures real emitted-signal evidence for later replay/backtest calibration.
It intentionally stores market/risk metadata only, never provider keys or env data.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class SignalJournal:
    """Write successful source alerts to JSONL."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def record(self, signal: object, *, sent_at: datetime, risk_text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "sent_at": sent_at.isoformat(),
            "chain": _enum_value(getattr(signal, "chain")),
            "signal_family": "v2_live",
            "topic_env_key": getattr(signal, "topic_env_key"),
            "feature": _enum_value(getattr(signal, "feature")),
            "token_address": getattr(signal, "token_address"),
            "symbol": getattr(signal, "symbol"),
            "name": getattr(signal, "name"),
            "price_usd": _number_or_none(getattr(signal, "price_usd", None)),
            "market_cap_usd": _number_or_none(getattr(signal, "market_cap_usd")),
            "liquidity_usd": _number_or_none(getattr(signal, "liquidity_usd")),
            "volume_24h_usd": _number_or_none(getattr(signal, "volume_24h_usd")),
            "buys_5m": getattr(signal, "buys_5m"),
            "buys_1h": getattr(signal, "buys_1h"),
            "buys_24h": getattr(signal, "buys_24h"),
            "sells_5m": getattr(signal, "sells_5m"),
            "sells_1h": getattr(signal, "sells_1h"),
            "sells_24h": getattr(signal, "sells_24h"),
            "pair_age_minutes": getattr(signal, "pair_age_minutes"),
            "price_change_5m": _number_or_none(getattr(signal, "price_change_5m")),
            "price_change_1h": _number_or_none(getattr(signal, "price_change_1h")),
            "price_change_24h": _number_or_none(getattr(signal, "price_change_24h")),
            "quality_score": getattr(signal, "quality_score"),
            "risk_level": _enum_value(getattr(signal, "risk_level", None)),
            "buy_tax_bps": getattr(signal, "buy_tax_bps", None),
            "sell_tax_bps": getattr(signal, "sell_tax_bps", None),
            "risk_reasons": list(getattr(signal, "risk_reasons", ())),
            "risk_text": risk_text,
            "reasons": list(getattr(signal, "reasons", ())),
            "url": getattr(signal, "url", None),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            handle.write("\n")


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
