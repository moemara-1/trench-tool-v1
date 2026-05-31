"""Best-wallet signal scoring for the high-conviction feed.

This module is deliberately provider-neutral: Moralis, Alchemy, Bitquery, or an
internal trade index can all feed the same candidate shape once they can provide
real PnL evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from best_signals import BestSignalCandidate


_SUPPORTED_PERIODS = {"week", "month", "year"}


@dataclass(frozen=True, slots=True)
class WalletPerformanceCandidate:
    chain: str
    wallet_address: str
    period: str
    realized_pnl_usd: float
    roi_pct: float
    win_rate: float
    trades: int
    wins: int
    losses: int
    top_tokens: tuple[str, ...] = ()
    evidence_url: str | None = None


def best_signal_from_wallet_performance(
    candidate: WalletPerformanceCandidate,
    *,
    min_score: int = 95,
) -> BestSignalCandidate | None:
    """Convert verified wallet-performance data into a Best Signals candidate."""

    period = candidate.period.lower().strip()
    if period not in _SUPPORTED_PERIODS:
        return None
    if not _has_enough_evidence(candidate):
        return None

    score = score_wallet_performance(candidate)
    if score < min_score:
        return None

    title_period = period.title()
    short_wallet = _short_wallet(candidate.wallet_address)
    reasons = [
        f"{period} top wallet: {candidate.roi_pct:.0f}% ROI",
        f"${candidate.realized_pnl_usd:,.0f} realized PnL",
        f"{candidate.win_rate:.0%} win rate across {candidate.trades} trades",
    ]
    if candidate.top_tokens:
        reasons.append("top hits: " + ", ".join(candidate.top_tokens[:3]))

    return BestSignalCandidate(
        source_label=f"Best Wallet {title_period}",
        chain=candidate.chain.lower().strip(),
        signal_family=f"best_wallet_{period}",
        token_address=candidate.wallet_address,
        symbol="WALLET",
        name=f"{short_wallet} Top Wallet",
        score=score,
        reasons=tuple(reasons),
        risk_text="wallet-performance signal; verify current token risk before entry",
        url=candidate.evidence_url,
    )


def best_signal_from_wallet_token_confluence(
    *,
    chain: str,
    token_address: str,
    token_symbol: str,
    token_name: str,
    period: str,
    wallet_candidates: tuple[WalletPerformanceCandidate, ...] | list[WalletPerformanceCandidate],
    min_score: int = 95,
    min_wallets: int = 2,
    risk_text: str | None = None,
    market_cap_usd: float | None = None,
    liquidity_usd: float | None = None,
    buys_5m: int | None = None,
    buys_1h: int | None = None,
    age_minutes: int | None = None,
    url: str | None = None,
) -> BestSignalCandidate | None:
    normalized_period = period.lower().strip()
    if normalized_period not in _SUPPORTED_PERIODS:
        return None

    eligible = tuple(
        candidate
        for candidate in wallet_candidates
        if candidate.period.lower().strip() == normalized_period and _has_enough_token_confluence_evidence(candidate)
    )
    if len(eligible) < min_wallets:
        return None

    score = score_wallet_token_confluence(eligible, period=normalized_period)
    if score < min_score:
        return None

    total_pnl = sum(candidate.realized_pnl_usd for candidate in eligible)
    total_trades = sum(candidate.trades for candidate in eligible)
    avg_roi = sum(candidate.roi_pct for candidate in eligible) / len(eligible)
    avg_win_rate = sum(candidate.win_rate for candidate in eligible) / len(eligible)
    reasons = [
        f"{len(eligible)} profitable wallets converged on ${token_symbol}",
        f"${total_pnl:,.0f} combined realized PnL",
        f"{avg_roi:.0f}% avg ROI",
        f"{avg_win_rate:.0%} avg win rate across {total_trades} trades",
    ]

    return BestSignalCandidate(
        source_label=f"Best Wallet Coin {normalized_period.title()}",
        chain=chain.lower().strip(),
        signal_family=f"best_wallet_coin_{normalized_period}",
        token_address=token_address,
        symbol=token_symbol or "UNKNOWN",
        name=token_name or token_symbol or "Unknown Token",
        score=score,
        reasons=tuple(reasons),
        risk_text=risk_text or "wallet confluence signal; verify token risk before entry",
        market_cap_usd=market_cap_usd,
        liquidity_usd=liquidity_usd,
        buys_5m=buys_5m,
        buys_1h=buys_1h,
        age_minutes=age_minutes,
        url=url,
    )


def score_wallet_performance(candidate: WalletPerformanceCandidate) -> int:
    if not _has_enough_evidence(candidate):
        return 0

    score = 60
    score += min(18, int(candidate.roi_pct / 25))
    score += min(12, int(candidate.realized_pnl_usd / 5_000))
    score += min(10, max(0, int((candidate.win_rate - 0.55) * 40)))
    score += min(8, candidate.trades // 2)
    if candidate.period.lower().strip() == "month":
        score += 3
    elif candidate.period.lower().strip() == "year":
        score += 4
    return max(0, min(100, score))


def score_wallet_token_confluence(
    wallet_candidates: tuple[WalletPerformanceCandidate, ...] | list[WalletPerformanceCandidate],
    *,
    period: str,
) -> int:
    eligible = [candidate for candidate in wallet_candidates if _has_enough_token_confluence_evidence(candidate)]
    if len(eligible) < 2:
        return 0

    total_pnl = sum(candidate.realized_pnl_usd for candidate in eligible)
    total_trades = sum(candidate.trades for candidate in eligible)
    avg_roi = sum(candidate.roi_pct for candidate in eligible) / len(eligible)
    avg_win_rate = sum(candidate.win_rate for candidate in eligible) / len(eligible)

    score = 74
    score += min(16, (len(eligible) - 1) * 8)
    score += min(8, int(total_pnl / 20_000))
    score += min(4, int(avg_roi / 200))
    score += min(4, max(0, int((avg_win_rate - 0.65) * 20)))
    score += min(4, total_trades // 20)
    if period == "month":
        score += 2
    elif period == "year":
        score += 3
    if total_pnl <= 1_000:
        score = min(score, 92)
    elif total_pnl < 5_000:
        score = min(score, 94)
    return max(0, min(100, score))



def _has_enough_evidence(candidate: WalletPerformanceCandidate) -> bool:
    return (
        candidate.trades >= 3
        and candidate.wins > candidate.losses
        and candidate.win_rate >= 0.55
        and candidate.realized_pnl_usd > 0
        and candidate.roi_pct >= 50
        and bool(candidate.wallet_address.strip())
    )


def _has_enough_token_confluence_evidence(candidate: WalletPerformanceCandidate) -> bool:
    return (
        candidate.trades >= 2
        and candidate.wins > candidate.losses
        and candidate.win_rate >= 0.55
        and candidate.realized_pnl_usd > 0
        and candidate.roi_pct >= 50
        and bool(candidate.wallet_address.strip())
    )


def _short_wallet(wallet_address: str) -> str:
    stripped = wallet_address.strip()
    if len(stripped) <= 12:
        return stripped
    return f"{stripped[:6]}...{stripped[-4:]}"
