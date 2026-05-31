"""Security and honeypot risk providers for EVM scans."""

from __future__ import annotations

from typing import Protocol

from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


class GetJsonClient(Protocol):
    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict | list:
        """Return JSON from a GET endpoint."""


_EVM_CHAIN_IDS = {
    Chain.ETHEREUM: "1",
    Chain.BSC: "56",
    Chain.BASE: "8453",
}

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class GoPlusRiskProvider:
    """Normalize GoPlus Token Security results into V2 risk reports."""

    def __init__(self, client: GetJsonClient | None = None, api_key: str | None = None):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self.client = client or AsyncJsonClient("goplus", headers=headers)

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        chain_id = _EVM_CHAIN_IDS.get(chain)
        if not chain_id:
            return RiskReport(reasons=["GoPlus unsupported chain"])

        try:
            data = await self.client.get_json(
                f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}",
                params={"contract_addresses": address.lower()},
            )
        except ProviderRateLimitError:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["GoPlus rate limited"])
        except Exception as exc:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=[f"GoPlus unavailable: {exc}"])

        if not isinstance(data, dict):
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["GoPlus returned unexpected payload"])

        result = data.get("result")
        if not isinstance(result, dict):
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["GoPlus returned no token result"])

        token = _lookup_address(result, address)
        if token is None:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["GoPlus returned no matching token result"])

        reasons: list[str] = []
        is_honeypot = _truthy(token.get("is_honeypot"))
        malicious_contract = False
        liquidity_pull_risk = False

        buy_tax_bps = _fraction_or_percent_to_bps(token.get("buy_tax"))
        sell_tax_bps = _fraction_or_percent_to_bps(token.get("sell_tax"))
        max_tax_bps = max(buy_tax_bps or 0, sell_tax_bps or 0)
        if max_tax_bps >= 500:
            reasons.append(f"tax {max_tax_bps / 100:.2f}%")

        if is_honeypot:
            reasons.append("honeypot flag")

        if _truthy(token.get("is_blacklisted")):
            malicious_contract = True
            reasons.append("blacklist control")

        if _truthy(token.get("is_mintable")):
            malicious_contract = True
            liquidity_pull_risk = True
            reasons.append("mintable supply")

        if _truthy(token.get("is_proxy")):
            malicious_contract = True
            reasons.append("proxy contract")

        if _falsey(token.get("is_open_source")):
            reasons.append("contract source is not verified")

        holder_data_unavailable = _int_or_none(token.get("holder_count")) == 0
        if holder_data_unavailable:
            reasons.append("holder data missing or zero holders reported")

        liquidity_locked = _liquidity_locked(token.get("lp_holders"))
        if liquidity_locked is False:
            liquidity_pull_risk = True
            reasons.append("liquidity is not locked")

        level = _level_for(
            is_honeypot=is_honeypot,
            max_tax_bps=max_tax_bps,
            malicious_contract=malicious_contract,
            liquidity_pull_risk=liquidity_pull_risk,
            has_unverified_source="contract source is not verified" in reasons,
        )
        return RiskReport(
            level=_medium_for_unindexed_holders(level, holder_data_unavailable),
            is_honeypot=is_honeypot,
            buy_tax_bps=buy_tax_bps,
            sell_tax_bps=sell_tax_bps,
            liquidity_locked=liquidity_locked,
            malicious_contract=malicious_contract,
            liquidity_pull_risk=liquidity_pull_risk,
            reasons=reasons or ["GoPlus found no high-risk flags"],
        )


class HoneypotRiskProvider:
    """Normalize Honeypot.is simulation results into V2 risk reports."""

    def __init__(self, client: GetJsonClient | None = None, api_key: str | None = None):
        headers = {"X-API-KEY": api_key} if api_key else None
        self.client = client or AsyncJsonClient("honeypot", headers=headers)

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        chain_id = _EVM_CHAIN_IDS.get(chain)
        if not chain_id:
            return RiskReport(reasons=["Honeypot.is unsupported chain"])

        try:
            data = await self.client.get_json(
                "https://api.honeypot.is/v2/IsHoneypot",
                params={"address": address, "chainID": chain_id},
            )
        except ProviderRateLimitError:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["Honeypot.is rate limited"])
        except Exception as exc:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=[f"Honeypot.is unavailable: {exc}"])

        if not isinstance(data, dict):
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["Honeypot.is returned unexpected payload"])

        honeypot_result = data.get("honeypotResult") if isinstance(data.get("honeypotResult"), dict) else {}
        simulation = data.get("simulationResult") if isinstance(data.get("simulationResult"), dict) else {}
        is_honeypot = bool(honeypot_result.get("isHoneypot"))
        buy_tax_bps = _percent_to_bps(simulation.get("buyTax"))
        sell_tax_bps = _percent_to_bps(simulation.get("sellTax"))
        max_tax_bps = max(buy_tax_bps or 0, sell_tax_bps or 0)

        reasons: list[str] = []
        if is_honeypot:
            reasons.append("honeypot simulation failed")
        if max_tax_bps >= 500:
            side = "sell" if (sell_tax_bps or 0) >= (buy_tax_bps or 0) else "buy"
            reasons.append(f"{side} tax {max_tax_bps / 100:.2f}%")

        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        summary_risk = str(summary.get("risk") or "").lower()
        token = data.get("token") if isinstance(data.get("token"), dict) else {}
        holder_count = _int_or_none(token.get("totalHolders"))
        malicious_contract = summary_risk in {"high", "critical"}
        holder_data_unavailable = holder_count == 0
        if holder_count == 0:
            reasons.append("holder data missing or zero holders reported")
        level = _level_for(
            is_honeypot=is_honeypot,
            max_tax_bps=max_tax_bps,
            malicious_contract=malicious_contract,
            liquidity_pull_risk=False,
            has_unverified_source=False,
        )
        return RiskReport(
            level=_medium_for_unindexed_holders(level, holder_data_unavailable),
            is_honeypot=is_honeypot,
            buy_tax_bps=buy_tax_bps,
            sell_tax_bps=sell_tax_bps,
            delayed_honeypot=is_honeypot,
            malicious_contract=malicious_contract,
            reasons=reasons or ["Honeypot.is simulation passed"],
        )


class CompositeRiskProvider:
    """Combine multiple risk providers without letting one failed provider break scans."""

    def __init__(self, providers: list[object]):
        self.providers = providers

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        if not self.providers:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["no risk provider configured"])

        reports: list[RiskReport] = []
        for provider in self.providers:
            fetch_risk = getattr(provider, "fetch_risk")
            reports.append(await fetch_risk(chain, address))

        return _combine_reports(reports)


def _combine_reports(reports: list[RiskReport]) -> RiskReport:
    if not reports:
        return RiskReport(level=RiskLevel.MEDIUM, reasons=["no risk provider configured"])

    reports = _ignore_provider_outage_when_clean_signal_exists(reports)
    highest_level = max((report.level for report in reports), key=lambda level: _RISK_ORDER[level])
    buy_taxes = [report.buy_tax_bps for report in reports if report.buy_tax_bps is not None]
    sell_taxes = [report.sell_tax_bps for report in reports if report.sell_tax_bps is not None]
    liquidity_locked_values = [
        report.liquidity_locked for report in reports if report.liquidity_locked is not None
    ]
    reasons: list[str] = []
    for report in reports:
        for reason in report.reasons:
            if reason not in reasons:
                reasons.append(reason)

    return RiskReport(
        level=highest_level,
        is_honeypot=any(report.is_honeypot for report in reports),
        buy_tax_bps=max(buy_taxes) if buy_taxes else None,
        sell_tax_bps=max(sell_taxes) if sell_taxes else None,
        liquidity_locked=False if False in liquidity_locked_values else (True if liquidity_locked_values else None),
        delayed_honeypot=any(report.delayed_honeypot for report in reports),
        malicious_contract=any(report.malicious_contract for report in reports),
        liquidity_pull_risk=any(report.liquidity_pull_risk for report in reports),
        reasons=reasons,
    )


def _ignore_provider_outage_when_clean_signal_exists(reports: list[RiskReport]) -> list[RiskReport]:
    clean_reports = [
        report
        for report in reports
        if report.level is RiskLevel.LOW and not _provider_outage_report(report)
    ]
    if not clean_reports:
        return reports

    blocking_reports = [
        report
        for report in reports
        if report.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        or (
            report.level is RiskLevel.MEDIUM
            and not _provider_outage_report(report)
        )
    ]
    return [*clean_reports, *blocking_reports]


def _provider_outage_report(report: RiskReport) -> bool:
    if report.level is not RiskLevel.MEDIUM:
        return False
    joined = " ".join(reason.lower() for reason in report.reasons)
    return any(
        marker in joined
        for marker in (
            "rate limited",
            "unavailable",
            "unexpected payload",
            "returned no token result",
            "returned no matching token result",
        )
    )


def _lookup_address(result: dict, address: str) -> dict | None:
    lowered = address.lower()
    for key, value in result.items():
        if str(key).lower() == lowered and isinstance(value, dict):
            return value
    for value in result.values():
        if isinstance(value, dict):
            return value
    return None


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _falsey(value: object) -> bool:
    return str(value).strip().lower() in {"0", "false", "no"}


def _fraction_or_percent_to_bps(value: object) -> int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    if number <= 1:
        return int(round(number * 10_000))
    return int(round(number * 100))


def _percent_to_bps(value: object) -> int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return int(round(number * 100))


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _liquidity_locked(lp_holders: object) -> bool | None:
    if not isinstance(lp_holders, list) or not lp_holders:
        return None
    locked_percent = 0.0
    for holder in lp_holders:
        if not isinstance(holder, dict) or not _truthy(holder.get("is_locked")):
            continue
        locked_percent += _float_or_none(holder.get("percent")) or 0.0
    return locked_percent >= 0.5


def _level_for(
    *,
    is_honeypot: bool,
    max_tax_bps: int,
    malicious_contract: bool,
    liquidity_pull_risk: bool,
    has_unverified_source: bool,
) -> RiskLevel:
    if is_honeypot:
        return RiskLevel.CRITICAL
    if max_tax_bps >= 2_000:
        return RiskLevel.HIGH
    if malicious_contract or liquidity_pull_risk or max_tax_bps >= 1_000:
        return RiskLevel.HIGH
    if has_unverified_source or max_tax_bps >= 500:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _medium_for_unindexed_holders(level: RiskLevel, holder_data_unavailable: bool) -> RiskLevel:
    if holder_data_unavailable and level is RiskLevel.LOW:
        return RiskLevel.MEDIUM
    return level
