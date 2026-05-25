"""Supply distribution summaries for bundle/team-control analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from trench_v2.core.models import HolderCluster, TokenScan


@dataclass(slots=True)
class SupplyDistributionReport:
    """Aggregated holder supply by behavior class."""

    team_insider_supply_percent: float = 0.0
    sniper_supply_percent: float = 0.0
    terminal_user_supply_percent: float = 0.0
    bundle_supply_percent: float = 0.0
    unrelated_supply_percent: float = 0.0
    high_team_control: bool = False
    drilldown_wallets: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class SupplyDistributionAnalyzer:
    """Group holder clusters into the categories described by the docs."""

    high_team_control_threshold = 35.0

    def summarize(self, scan: TokenScan) -> SupplyDistributionReport:
        report = SupplyDistributionReport()

        for cluster in scan.holder_clusters:
            label = cluster.label.strip().lower().replace("-", "_")
            self._add_cluster(report, cluster, label)

        if scan.bundle_supply_percent:
            report.bundle_supply_percent = max(report.bundle_supply_percent, round(scan.bundle_supply_percent, 2))

        report.high_team_control = report.team_insider_supply_percent >= self.high_team_control_threshold
        report.team_insider_supply_percent = round(report.team_insider_supply_percent, 2)
        report.sniper_supply_percent = round(report.sniper_supply_percent, 2)
        report.terminal_user_supply_percent = round(report.terminal_user_supply_percent, 2)
        report.bundle_supply_percent = round(report.bundle_supply_percent, 2)
        report.unrelated_supply_percent = round(report.unrelated_supply_percent, 2)
        return report

    def _add_cluster(
        self,
        report: SupplyDistributionReport,
        cluster: HolderCluster,
        label: str,
    ) -> None:
        if label in {"team", "insider", "team_insider", "creator", "dev"}:
            report.team_insider_supply_percent += cluster.supply_percent
            report.drilldown_wallets.extend(cluster.wallets)
        elif label in {"sniper", "snipers"}:
            report.sniper_supply_percent += cluster.supply_percent
            report.drilldown_wallets.extend(cluster.wallets)
        elif label in {"terminal", "terminal_user", "terminal_users", "bot", "multi_wallet_bot"}:
            report.terminal_user_supply_percent += cluster.supply_percent
            report.drilldown_wallets.extend(cluster.wallets)
        elif label in {"bundle", "bundled"}:
            report.bundle_supply_percent += cluster.supply_percent
            report.drilldown_wallets.extend(cluster.wallets)
        else:
            report.unrelated_supply_percent += cluster.supply_percent

        report.evidence.extend(cluster.evidence)
