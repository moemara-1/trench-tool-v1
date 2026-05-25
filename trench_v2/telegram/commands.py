"""Telegram command parsing and formatting for V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trench_v2.core.models import Chain, TokenScan
from trench_v2.engine.supply import SupplyDistributionAnalyzer


SUPPORTED_COMMANDS = ("/scan", "/analyze", "/track", "/og", "/simulate", "/watch", "/status")


class ScannerService(Protocol):
    async def scan(self, address: str, chain: Chain | None = None) -> TokenScan:
        """Scan a token."""

    async def analyze(self, address: str, chain: Chain | None = None) -> TokenScan:
        """Analyze a token."""

    async def find_og(self, query: str, chain: Chain | None = None) -> list[TokenScan]:
        """Find OG tokens."""

    async def simulate(self, address: str, chain: Chain | None = None) -> TokenScan:
        """Simulate a token."""


class WatchlistService(Protocol):
    async def track(self, address: str, chain: Chain | None = None) -> str:
        """Track a token."""

    async def watch(self, address: str, chain: Chain | None = None) -> str:
        """Watch a token."""


@dataclass(slots=True)
class CommandResponse:
    ok: bool
    text: str
    parse_mode: str = "HTML"


class CommandRouter:
    """Handles the private Telegram V2 command surface."""

    def __init__(self, scanner: ScannerService, watchlist: WatchlistService):
        self.scanner = scanner
        self.watchlist = watchlist
        self.supply_analyzer = SupplyDistributionAnalyzer()

    async def handle(self, text: str) -> CommandResponse:
        command, args = self._split_command(text)

        if command == "/scan":
            chain, address = self._parse_chain_address(args)
            scan = await self.scanner.scan(address, chain)
            return CommandResponse(ok=True, text=self._format_scan("SCAN", scan))

        if command == "/analyze":
            chain, address = self._parse_chain_address(args)
            scan = await self.scanner.analyze(address, chain)
            return CommandResponse(ok=True, text=self._format_scan("ANALYZE", scan))

        if command == "/simulate":
            chain, address = self._parse_chain_address(args)
            scan = await self.scanner.simulate(address, chain)
            return CommandResponse(ok=True, text=self._format_scan("SIMULATE", scan))

        if command == "/og":
            chain, query = self._parse_chain_address(args)
            scans = await self.scanner.find_og(query, chain)
            body = "\n\n".join(self._format_scan("OG", scan) for scan in scans)
            return CommandResponse(ok=True, text=body or "No OG candidates found.")

        if command == "/track":
            chain, address = self._parse_chain_address(args)
            target_id = await self.watchlist.track(address, chain)
            return CommandResponse(ok=True, text=f"Now watching <code>{target_id}</code>.")

        if command == "/watch":
            chain, address = self._parse_chain_address(args)
            target_id = await self.watchlist.watch(address, chain)
            return CommandResponse(ok=True, text=f"Now watching <code>{target_id}</code>.")

        if command == "/status":
            return CommandResponse(ok=True, text="V2 command surface online.")

        return CommandResponse(
            ok=False,
            text="Unsupported command. Use: " + ", ".join(SUPPORTED_COMMANDS),
        )

    def _split_command(self, text: str) -> tuple[str, list[str]]:
        parts = text.strip().split()
        if not parts:
            return "", []
        return parts[0].lower(), parts[1:]

    def _parse_chain_address(self, args: list[str]) -> tuple[Chain | None, str]:
        if not args:
            raise ValueError("Command requires a token address or query.")

        try:
            chain = Chain.from_hint(args[0])
            if len(args) < 2:
                raise ValueError("Command requires an address after the chain hint.")
            return chain, args[1]
        except ValueError:
            return None, args[0]

    def _format_scan(self, title: str, scan: TokenScan) -> str:
        mc = self._money(scan.market_cap_usd)
        liquidity = self._money(scan.liquidity_usd)
        reasons = ", ".join(scan.signals.reasons or scan.risk.reasons or ["no reasons recorded"])
        metadata_lines = self._metadata_lines(scan)
        return (
            f"<b>{title} {scan.chain.label}</b>\n"
            f"${scan.symbol} {scan.name}\n"
            f"MC: {mc} | Liq: {liquidity}\n"
            f"{metadata_lines}"
            f"Confidence: {scan.signals.confidence}/100 | Risk: {scan.signals.risk}/100\n"
            f"Risk level: {scan.risk.level.value}\n"
            f"Why: {reasons}\n"
            f"<code>{scan.address}</code>"
        )

    def _metadata_lines(self, scan: TokenScan) -> str:
        lines: list[str] = []
        if scan.is_pre_bonded or scan.pool_type:
            prebond = "yes" if scan.is_pre_bonded else "no"
            pool = scan.pool_type or "?"
            lines.append(f"Pre-bond: {prebond} | Pool: {pool}")

        if scan.holder_clusters:
            report = self.supply_analyzer.summarize(scan)
            lines.append(
                "Supply: "
                f"Team/insiders: {report.team_insider_supply_percent:.1f}% | "
                f"Snipers: {report.sniper_supply_percent:.1f}% | "
                f"Terminal: {report.terminal_user_supply_percent:.1f}%"
            )

        risk_lines = self._risk_metadata_lines(scan)
        lines.extend(risk_lines)

        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def _risk_metadata_lines(self, scan: TokenScan) -> list[str]:
        risk = scan.risk
        lines: list[str] = []
        if risk.is_honeypot:
            lines.append("Honeypot: yes")
        if risk.buy_tax_bps is not None or risk.sell_tax_bps is not None:
            buy_tax = self._bps(risk.buy_tax_bps)
            sell_tax = self._bps(risk.sell_tax_bps)
            lines.append(f"Buy tax: {buy_tax} | Sell tax: {sell_tax}")
        if risk.liquidity_locked is not None:
            locked = "yes" if risk.liquidity_locked else "no"
            lines.append(f"Liquidity locked: {locked}")
        if risk.malicious_contract:
            lines.append("Malicious contract: yes")
        if risk.liquidity_pull_risk:
            lines.append("Liquidity pull risk: yes")
        return lines

    def _money(self, value: float | None) -> str:
        if value is None:
            return "?"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"${value / 1_000:.1f}k"
        return f"${value:.0f}"

    def _bps(self, value: int | None) -> str:
        if value is None:
            return "?"
        return f"{value / 100:.2f}%"
