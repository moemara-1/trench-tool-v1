"""Security and honeypot risk providers for EVM scans."""

from __future__ import annotations

from typing import Protocol

from trench_v2.core.models import Chain, RiskLevel, RiskReport
from trench_v2.providers.http import AsyncJsonClient, ProviderRateLimitError


class GetJsonClient(Protocol):
    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict | list:
        """Return JSON from a GET endpoint."""


class PostJsonClient(Protocol):
    async def post_json(self, url: str, payload: dict[str, object]) -> dict:
        """Return JSON from a JSON-RPC endpoint."""


_EVM_CHAIN_IDS = {
    Chain.ETHEREUM: "1",
    Chain.BSC: "56",
    Chain.BASE: "8453",
}

# Canonical contracts published at https://docs.robinhood.com/chain/contracts/.
_ROBINHOOD_CANONICAL_TOKEN_ADDRESSES = frozenset(
    address.lower()
    for address in (
        "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73",
        "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
        "0xaF3D76f1834A1d425780943C99Ea8A608f8a93f9",
        "0x86923f96303D656E4aa86D9d42D1e57ad2023fdC",
        "0x12f190a9F9d7D37a250758b26824B97CE941bF54",
        "0xad25Ac6C84D497db898fa1E8387bf6Af3532a1c4",
        "0x822CC93fFD030293E9842c30BBD678F530701867",
        "0x6330D8C3178a418788dF01a47479c0ce7CCF450b",
        "0xdF0992E440dD0be65BD8439b609d6D4366bf1CB5",
        "0x5f10A1C971B69e47e059e1dC91901B59b3fB49C3",
        "0x2e0847E8910a9732eB3fb1bb4b70a580ADAD4FE3",
        "0xc72b96e0E48ecd4DC75E1e45396e26300BC39681",
        "0xc0D6457C16Cc70d6790Dd43521C899C87ce02f35",
        "0xe93237C50D904957Cf27E7B1133b510C669c2e74",
        "0xfF080c8ce2E5feadaCa0Da81314Ae59D232d4afD",
        "0xd0601CE157Db5bdC3162BbaC2a2C8aF5320D9EEC",
        "0xb0992820E760d836549ba69BC7598b4af75dEE03",
        "0x894E1EC2D74FFE5AEF8Dc8A9e84686acCB964F2A",
        "0xB90A19fF0Af67f7779afF50A882A9CfF42446400",
        "0x4a0E65A3EcceC6dBe60AE065F2e7bb85Fae35eEa",
        "0x322F0929c4625eD5bAd873c95208D54E1c003b2d",
        "0xd917B029C761D264c6A312BBbcDA868658eF86a6",
        "0xD5f3879160bc7c32ebb4dC785F8a4F505888de68",
        "0x92FD66527192E3e61d4DDd13322Aa222DE86F9B5",
        "0x411eFb0E7f985935DAec3D4C3ebaEa0d0AD7D89f",
        "0x117cc2133c37B721F49dE2A7a74833232B3B4C0C",
        "0xa30FA36Db767ad9eD3f7a60fC79526fB4d56D344",
    )
)

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

_EIP1967_IMPLEMENTATION_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)
_OWNER_SELECTOR = "0x8da5cb5b"
_ZERO_ADDRESS = "0x" + "0" * 40


class GoPlusRiskProvider:
    """Normalize GoPlus Token Security results into V2 risk reports."""

    def __init__(self, client: GetJsonClient | None = None, api_key: str | None = None):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self.client = client or AsyncJsonClient("goplus", headers=headers)

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        chain_id = _EVM_CHAIN_IDS.get(chain)
        if not chain_id:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["GoPlus unsupported chain"])

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
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["Honeypot.is unsupported chain"])

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


class RobinhoodRiskProvider:
    """Use native RPC checks where third-party RH security indexers are unavailable."""

    def __init__(self, rpc_url: str | None = None, client: PostJsonClient | None = None):
        self.rpc_url = rpc_url
        self.client = client or AsyncJsonClient("robinhood-onchain-risk")

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        if chain is not Chain.ROBINHOOD:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["Robinhood risk provider unsupported chain"])
        if address.lower() in _ROBINHOOD_CANONICAL_TOKEN_ADDRESSES:
            return RiskReport(
                level=RiskLevel.LOW,
                buy_tax_bps=0,
                sell_tax_bps=0,
                reasons=["canonical Robinhood Chain token"],
            )
        if not self.rpc_url:
            return RiskReport(
                level=RiskLevel.MEDIUM,
                reasons=["Robinhood Chain independent security indexers unavailable"],
            )

        try:
            code = await self._rpc("eth_getCode", [address, "latest"])
            if not _has_deployed_code(code):
                return RiskReport(
                    level=RiskLevel.HIGH,
                    malicious_contract=True,
                    reasons=["token address has no deployed bytecode"],
                )

            implementation = await self._rpc(
                "eth_getStorageAt",
                [address, _EIP1967_IMPLEMENTATION_SLOT, "latest"],
            )
            if _has_nonzero_hex(implementation):
                return RiskReport(
                    level=RiskLevel.HIGH,
                    malicious_contract=True,
                    reasons=["upgradeable proxy contract"],
                )

            owner_result = await self._rpc(
                "eth_call",
                [{"to": address, "data": _OWNER_SELECTOR}, "latest"],
            )
            owner = _address_from_abi_word(owner_result)
            if owner is None:
                return RiskReport(
                    level=RiskLevel.MEDIUM,
                    reasons=["Robinhood on-chain owner state unavailable"],
                )
            if owner != _ZERO_ADDRESS:
                return RiskReport(
                    level=RiskLevel.HIGH,
                    malicious_contract=True,
                    reasons=["active owner control"],
                )

            return RiskReport(
                level=RiskLevel.LOW,
                reasons=["on-chain code present and owner renounced"],
            )
        except ProviderRateLimitError:
            return RiskReport(level=RiskLevel.MEDIUM, reasons=["Robinhood on-chain risk check rate limited"])
        except Exception as exc:
            return RiskReport(
                level=RiskLevel.MEDIUM,
                reasons=[f"Robinhood on-chain risk check unavailable: {type(exc).__name__}"],
            )

    async def _rpc(self, method: str, params: list[object]) -> object:
        if not self.rpc_url:
            raise ValueError("missing Robinhood RPC URL")
        payload = await self.client.post_json(
            self.rpc_url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            },
        )
        if not isinstance(payload, dict):
            raise ValueError("non-object JSON-RPC response")
        if payload.get("error"):
            raise ValueError("JSON-RPC error")
        if "result" not in payload:
            raise ValueError("missing JSON-RPC result")
        return payload["result"]

class CompositeRiskProvider:
    """Combine multiple risk providers without letting one failed provider break scans."""

    def __init__(
        self,
        providers: list[object],
        chain_overrides: dict[Chain, object] | None = None,
    ):
        self.providers = providers
        self.chain_overrides = chain_overrides or {}

    async def fetch_risk(self, chain: Chain, address: str) -> RiskReport:
        override = self.chain_overrides.get(chain)
        if override is not None:
            return await getattr(override, "fetch_risk")(chain, address)

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


def _has_deployed_code(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _has_nonzero_hex(value)


def _has_nonzero_hex(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("0x"):
        return False
    return any(character != "0" for character in value[2:].lower())


def _address_from_abi_word(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    raw = value[2:].lower()
    if len(raw) < 40:
        return None
    address = raw[-40:]
    if any(character not in "0123456789abcdef" for character in address):
        return None
    return "0x" + address


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
