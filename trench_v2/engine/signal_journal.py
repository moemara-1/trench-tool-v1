"""Append-only journal for V2 source alerts.

This captures real emitted-signal evidence for later replay/backtest calibration.
It intentionally stores market/risk metadata only, never provider keys or env data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


class SignalJournal:
    """Write successful source alerts to JSONL."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def recent_dedupe_keys(
        self,
        *,
        now: datetime | None = None,
        max_age_hours: int = 24,
    ) -> set[str]:
        if not self.path.exists():
            return set()

        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        cutoff = reference - timedelta(hours=max(0, max_age_hours))
        keys: set[str] = set()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                        sent_at = datetime.fromisoformat(
                            str(row.get("sent_at") or "").replace("Z", "+00:00")
                        )
                    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=timezone.utc)
                    if sent_at < cutoff:
                        continue
                    topic = str(row.get("topic_env_key") or "").strip()
                    chain = str(row.get("chain") or "").strip()
                    address = str(row.get("token_address") or "").strip().lower()
                    if topic and chain and address:
                        keys.add(f"{topic}:{chain}:{address}")
        except OSError:
            return set()
        return keys

    def record(self, signal: object, *, sent_at: datetime, risk_text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "record_type": "source_signal_sent",
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


    def record_best(self, candidate: object, *, sent_at: datetime) -> None:
        """Record a candidate only after the Best Signals Telegram send succeeds."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "record_type": "best_signal_sent",
            "event_id": _best_signal_event_id(candidate, sent_at),
            "sent_at": sent_at.isoformat(),
            "source_label": getattr(candidate, "source_label"),
            "chain": getattr(candidate, "chain"),
            "signal_family": getattr(candidate, "signal_family"),
            "provenance": getattr(candidate, "provenance", "structured"),
            "confluence_sources": list(
                getattr(candidate, "effective_confluence_sources", getattr(candidate, "confluence_sources", ()))
            ),
            "token_address": getattr(candidate, "token_address"),
            "symbol": getattr(candidate, "symbol"),
            "name": getattr(candidate, "name"),
            "price_usd": _number_or_none(getattr(candidate, "price_usd", None)),
            "score": getattr(candidate, "score"),
            "market_cap_usd": _number_or_none(getattr(candidate, "market_cap_usd", None)),
            "liquidity_usd": _number_or_none(getattr(candidate, "liquidity_usd", None)),
            "volume_24h_usd": _number_or_none(getattr(candidate, "volume_24h_usd", None)),
            "buys_5m": getattr(candidate, "buys_5m", None),
            "buys_1h": getattr(candidate, "buys_1h", None),
            "sells_5m": getattr(candidate, "sells_5m", None),
            "sells_1h": getattr(candidate, "sells_1h", None),
            "pair_age_minutes": getattr(candidate, "age_minutes", None),
            "price_change_5m": _number_or_none(getattr(candidate, "price_change_5m", None)),
            "price_change_1h": _number_or_none(getattr(candidate, "price_change_1h", None)),
            "price_change_24h": _number_or_none(getattr(candidate, "price_change_24h", None)),
            "risk_text": getattr(candidate, "risk_text", None),
            "reasons": list(getattr(candidate, "reasons", ())),
            "url": getattr(candidate, "url", None),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            handle.write(chr(10))


    def record_feedback(
        self,
        *,
        chain: str,
        token_address: str,
        symbol: str,
        verdict: str,
        entry_price_usd: float,
        observed_price_usd: float,
        related_sent_at: datetime,
        recorded_at: datetime,
        source: str,
    ) -> None:
        """Persist explicit outcome feedback without changing eligibility by itself."""

        normalized_verdict = verdict.strip().lower()
        if normalized_verdict not in {"positive", "negative"}:
            raise ValueError("verdict must be positive or negative")
        if entry_price_usd <= 0 or observed_price_usd < 0:
            raise ValueError("feedback prices must contain a positive entry and nonnegative observation")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "record_type": "best_signal_feedback",
            "event_id": _best_signal_feedback_event_id(
                chain=chain,
                token_address=token_address,
                related_sent_at=related_sent_at,
                verdict=normalized_verdict,
            ),
            "recorded_at": recorded_at.isoformat(),
            "related_sent_at": related_sent_at.isoformat(),
            "chain": chain.strip().lower(),
            "token_address": token_address,
            "symbol": symbol,
            "verdict": normalized_verdict,
            "source": source,
            "entry_price_usd": float(entry_price_usd),
            "observed_price_usd": float(observed_price_usd),
            "observed_multiple": round(observed_price_usd / entry_price_usd, 4),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            handle.write(chr(10))


def _best_signal_feedback_event_id(
    *,
    chain: str,
    token_address: str,
    related_sent_at: datetime,
    verdict: str,
) -> str:
    identity = "|".join(
        (
            "best_signal_feedback",
            related_sent_at.isoformat(),
            chain.strip().lower(),
            token_address.lower(),
            verdict,
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()[:24]

def _best_signal_event_id(candidate: object, sent_at: datetime) -> str:
    identity = "|".join(
        (
            "best_signal_sent",
            sent_at.isoformat(),
            str(getattr(candidate, "chain")),
            str(getattr(candidate, "token_address")).lower(),
            str(getattr(candidate, "signal_family")),
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()[:24]

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
