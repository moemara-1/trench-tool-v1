"""Replay/backtest primitives for calibrating alert quality from outcomes."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from best_signals import BestSignalPerformance


@dataclass(frozen=True, slots=True)
class PricePoint:
    timestamp: datetime
    price_usd: float


@dataclass(frozen=True, slots=True)
class SignalReplayEvent:
    chain: str
    token_address: str
    signal_family: str
    score: int
    sent_at: datetime
    entry_price_usd: float


@dataclass(frozen=True, slots=True)
class SignalReplayOutcome:
    event: SignalReplayEvent
    max_multiple: float
    max_drawdown_pct: float
    minutes_to_peak: int | None
    hit_2x: bool
    rugged: bool


def evaluate_signal_outcome(
    event: SignalReplayEvent,
    prices: list[PricePoint] | tuple[PricePoint, ...],
    *,
    horizon: timedelta = timedelta(hours=24),
    hit_multiple: float = 2.0,
    rug_drawdown_pct: float = 80.0,
) -> SignalReplayOutcome:
    """Evaluate one alert against later prices inside a replay horizon."""

    if event.entry_price_usd <= 0:
        raise ValueError("entry_price_usd must be positive")
    if hit_multiple <= 1:
        raise ValueError("hit_multiple must be greater than 1")
    if rug_drawdown_pct <= 0 or rug_drawdown_pct > 100:
        raise ValueError("rug_drawdown_pct must be in (0, 100]")

    sent_at = _normalize_time(event.sent_at)
    horizon_end = sent_at + horizon
    window = sorted(
        (
            PricePoint(_normalize_time(point.timestamp), point.price_usd)
            for point in prices
            if sent_at <= _normalize_time(point.timestamp) <= horizon_end and point.price_usd > 0
        ),
        key=lambda point: point.timestamp,
    )

    if not window:
        return SignalReplayOutcome(
            event=event,
            max_multiple=0.0,
            max_drawdown_pct=0.0,
            minutes_to_peak=None,
            hit_2x=False,
            rugged=False,
        )

    peak = max(window, key=lambda point: point.price_usd)
    trough_price = min(point.price_usd for point in window)
    max_multiple = peak.price_usd / event.entry_price_usd
    max_drawdown_pct = max(0.0, (event.entry_price_usd - trough_price) / event.entry_price_usd * 100)
    minutes_to_peak = int((peak.timestamp - sent_at).total_seconds() // 60)

    return SignalReplayOutcome(
        event=event,
        max_multiple=round(max_multiple, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        minutes_to_peak=max(0, minutes_to_peak),
        hit_2x=max_multiple >= hit_multiple,
        rugged=max_drawdown_pct >= rug_drawdown_pct,
    )


def summarize_outcomes(outcomes: list[SignalReplayOutcome] | tuple[SignalReplayOutcome, ...]) -> dict[str, dict]:
    """Summarize replay performance by family and broad score band."""

    groups: dict[str, list[SignalReplayOutcome]] = defaultdict(list)
    for outcome in outcomes:
        groups[outcome.event.signal_family].append(outcome)
        groups[f"score_band:{_score_band(outcome.event.score)}"].append(outcome)
    return {name: _summarize_group(group) for name, group in sorted(groups.items())}


def performance_profiles_from_outcomes(
    outcomes: list[SignalReplayOutcome] | tuple[SignalReplayOutcome, ...],
) -> dict[str, BestSignalPerformance]:
    """Build Best Signals performance profiles from replay outcomes by family."""

    groups: dict[str, list[SignalReplayOutcome]] = defaultdict(list)
    for outcome in outcomes:
        groups[outcome.event.signal_family].append(outcome)

    profiles: dict[str, BestSignalPerformance] = {}
    for family, family_outcomes in groups.items():
        count = len(family_outcomes)
        multiples = sorted(outcome.max_multiple for outcome in family_outcomes)
        profiles[family] = BestSignalPerformance(
            sample_size=count,
            hit_2x_rate=sum(1 for outcome in family_outcomes if outcome.hit_2x) / count,
            rug_rate=sum(1 for outcome in family_outcomes if outcome.rugged) / count,
            median_max_multiple=_median(multiples),
            average_max_multiple=sum(multiples) / count,
        )
    return profiles


def load_performance_profiles(path: str | Path) -> dict[str, BestSignalPerformance]:
    """Load Best Signals performance profiles from a JSON object keyed by family."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("performance profile file must contain a JSON object")

    profiles: dict[str, BestSignalPerformance] = {}
    for family, raw_profile in data.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"performance profile for {family} must be an object")
        profiles[str(family)] = BestSignalPerformance(
            sample_size=_required_int(raw_profile, "sample_size"),
            hit_2x_rate=_required_float(raw_profile, "hit_2x_rate"),
            rug_rate=_required_float(raw_profile, "rug_rate"),
            median_max_multiple=_required_float(raw_profile, "median_max_multiple"),
            average_max_multiple=_required_float(raw_profile, "average_max_multiple"),
        )
    return profiles


def load_signal_replay_events_from_journal(path: str | Path) -> list[SignalReplayEvent]:
    """Load replayable source-alert events from the V2 JSONL signal journal."""

    journal_path = Path(path)
    if not journal_path.exists():
        return []

    events: list[SignalReplayEvent] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        event = _event_from_journal_record(record)
        if event:
            events.append(event)
    return events


def _summarize_group(outcomes: list[SignalReplayOutcome]) -> dict:
    count = len(outcomes)
    if count == 0:
        return {
            "count": 0,
            "hit_2x_rate": 0.0,
            "rug_rate": 0.0,
            "average_max_multiple": 0.0,
            "median_max_multiple": 0.0,
        }
    multiples = sorted(outcome.max_multiple for outcome in outcomes)
    return {
        "count": count,
        "hit_2x_rate": round(sum(1 for outcome in outcomes if outcome.hit_2x) / count, 4),
        "rug_rate": round(sum(1 for outcome in outcomes if outcome.rugged) / count, 4),
        "average_max_multiple": round(sum(multiples) / count, 4),
        "median_max_multiple": round(_median(multiples), 4),
    }


def _score_band(score: int) -> str:
    if score >= 95:
        return "95_100"
    if score >= 80:
        return "80_94"
    return "0_79"


def _median(values: list[float]) -> float:
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / 2


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _required_int(values: dict, key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_float(values: dict, key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _event_from_journal_record(record: dict) -> SignalReplayEvent | None:
    chain = _nonempty_str(record.get("chain"))
    token_address = _nonempty_str(record.get("token_address"))
    signal_family = _nonempty_str(record.get("signal_family"))
    sent_at = _datetime_from_record(record.get("sent_at"))
    entry_price = _positive_float(record.get("price_usd"))
    score = _score_from_record(record)
    if not chain or not token_address or not signal_family or not sent_at or entry_price is None or score is None:
        return None
    return SignalReplayEvent(
        chain=chain,
        token_address=token_address,
        signal_family=signal_family,
        score=score,
        sent_at=sent_at,
        entry_price_usd=entry_price,
    )


def _nonempty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _datetime_from_record(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return _normalize_time(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


def _score_from_record(record: dict) -> int | None:
    value = record.get("quality_score", record.get("score"))
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, min(100, value))
