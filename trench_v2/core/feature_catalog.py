"""Doc-backed V2 feature catalog.

The catalog is intentionally data-first: provider implementations can attach to
these specs without rediscovering thresholds, topic names, and command surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from trench_v2.core.models import Chain
from trench_v2.telegram.topics import TopicFeature, topic_env_key


class FeatureKind(str, Enum):
    COMMAND = "command"
    ALERT = "alert"
    SUPPLY_ANALYSIS = "supply_analysis"
    WALLET_ANALYSIS = "wallet_analysis"
    DEPLOY_MONITOR = "deploy_monitor"
    PRE_LIVE = "pre_live"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    id: str
    title: str
    kind: FeatureKind
    chain: Chain | None
    topic_feature: TopicFeature
    source: str
    min_native_amount: float | None = None
    max_market_cap_usd: float | None = None
    min_inactive_days: int | None = None
    min_wallets: int | None = None
    notes: str = ""


class FeatureCatalog:
    def __init__(self, specs: list[FeatureSpec]):
        self._specs = {spec.id: spec for spec in specs}

    @classmethod
    def default(cls) -> "FeatureCatalog":
        specs: list[FeatureSpec] = [
            FeatureSpec(
                id="ravnview_scan",
                title="RAVNView Scan",
                kind=FeatureKind.COMMAND,
                chain=None,
                topic_feature=TopicFeature.SCAN,
                source="RAVNView docs",
                notes="Scan token holders, wallet histories, and supply distribution.",
            ),
            FeatureSpec(
                id="ravnview_analyze",
                title="RAVNView Analyze",
                kind=FeatureKind.COMMAND,
                chain=None,
                topic_feature=TopicFeature.ANALYZE,
                source="RAVN clipping /analyze",
                notes="Detect delayed honeypots, liquidity pulls, and malicious contracts.",
            ),
            FeatureSpec(
                id="ravnview_track",
                title="RAVN Tracker",
                kind=FeatureKind.PRE_LIVE,
                chain=None,
                topic_feature=TopicFeature.TRACK,
                source="RAVN clipping /track",
                notes="Track team wallets before and after live trading.",
            ),
            FeatureSpec(
                id="ravnview_og",
                title="RAVNView OG",
                kind=FeatureKind.COMMAND,
                chain=Chain.ETHEREUM,
                topic_feature=TopicFeature.OG,
                source="RAVN clipping /og",
                notes="Suppress older ETH tax tokens and show pre-bond/pool type.",
            ),
            FeatureSpec(
                id="ravnview_simulate",
                title="RAVNView Simulate",
                kind=FeatureKind.PRE_LIVE,
                chain=None,
                topic_feature=TopicFeature.SIMULATE,
                source="RAVN clipping /simulate",
                notes="Pre-live sniper simulation surface.",
            ),
            FeatureSpec(
                id="ravn_bundle_supply",
                title="RAVN Bundle/Supply Analysis",
                kind=FeatureKind.SUPPLY_ANALYSIS,
                chain=None,
                topic_feature=TopicFeature.BUNDLES,
                source="RAVN bundle scanner docs",
                notes="Team/insider, sniper, and terminal-user supply control with drilldown wallets.",
            ),
        ]
        specs.extend(_bbb_specs())
        return cls(specs)

    def get(self, feature_id: str) -> FeatureSpec:
        return self._specs[feature_id]

    def all(self) -> tuple[FeatureSpec, ...]:
        return tuple(self._specs.values())

    def topic_env_key(self, feature_id: str) -> str:
        spec = self.get(feature_id)
        if spec.chain is None:
            raise ValueError(f"Feature {feature_id} is not chain-specific")
        return topic_env_key(spec.chain, spec.topic_feature)


def _bbb_specs() -> list[FeatureSpec]:
    return [
        FeatureSpec(
            "sol_dormants",
            "SOL Dormants",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.DORMANTS,
            "BBB Solana Dormants",
            min_native_amount=3.0,
            notes="Dormant SOL buys with wallet/profile quick tasks.",
        ),
        FeatureSpec(
            "sol_low_mc_big_freshies",
            "SOL Low MC Big Freshies",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.LOW_MC_FRESHIES,
            "BBB Solana Low MC Big Freshies",
            min_native_amount=5.0,
            max_market_cap_usd=5_000_000,
        ),
        FeatureSpec(
            "sol_freshies_sells",
            "SOL Freshies Sells",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.FRESHIES_SELLS,
            "BBB Solana Freshies Sells",
        ),
        FeatureSpec(
            "sol_semi_dormants",
            "SOL Semi-Dormants",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.SEMI_DORMANTS,
            "BBB Solana Semi-Dormants",
        ),
        FeatureSpec(
            "sol_semi_dormants_sells",
            "SOL Semi-Dormants Sells",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.SEMI_DORMANTS_SELLS,
            "BBB Solana Semi-Dormants Sells",
        ),
        FeatureSpec(
            "sol_sns_buys",
            "SOL SNS Buys",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.SNS,
            "BBB Solana SNS Buys",
        ),
        FeatureSpec(
            "sol_vanish_buys",
            "SOL Vanish Buys",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.VANISH,
            "BBB Solana Vanish Buys",
        ),
        FeatureSpec(
            "sol_vanish_sells",
            "SOL Vanish Sells",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.VANISH_SELLS,
            "BBB Solana Vanish Sells",
        ),
        FeatureSpec(
            "sol_bundles",
            "SOL Bundles",
            FeatureKind.SUPPLY_ANALYSIS,
            Chain.SOLANA,
            TopicFeature.BUNDLES,
            "BBB Solana Bundles",
        ),
        FeatureSpec(
            "sol_patterns",
            "SOL Patterns",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.PATTERNS,
            "BBB Solana Patterns",
        ),
        FeatureSpec(
            "sol_freshies_wizard",
            "SOL Freshies Wizard",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.WIZARD,
            "BBB Solana Freshies Wizard",
        ),
        FeatureSpec(
            "sol_migrations_tracker",
            "SOL Migrations Tracker",
            FeatureKind.PRE_LIVE,
            Chain.SOLANA,
            TopicFeature.MIGRATIONS_TRACKER,
            "BBB Solana Migrations Tracker",
        ),
        FeatureSpec(
            "sol_old_migrations",
            "SOL Old Migrations",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.OLD_MIGRATIONS,
            "BBB Solana Old Migrations",
        ),
        FeatureSpec(
            "sol_dormant_deploys",
            "SOL Dormant Deploys",
            FeatureKind.DEPLOY_MONITOR,
            Chain.SOLANA,
            TopicFeature.DORMANT_DEPLOYS,
            "BBB Solana Dormant Deploys",
        ),
        FeatureSpec(
            "sol_jupiter_dca",
            "SOL Jupiter DCA",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.JUPITER_DCA,
            "BBB Solana Jupiter DCA",
        ),
        FeatureSpec(
            "sol_liquidity_inflows",
            "SOL Liquidity Inflows",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.LIQUIDITY_INFLOWS,
            "BBB Solana Liquidity Inflows",
        ),
        FeatureSpec(
            "sol_boop_deploys",
            "SOL Boop Deploys",
            FeatureKind.DEPLOY_MONITOR,
            Chain.SOLANA,
            TopicFeature.BOOP_DEPLOYS,
            "BBB Solana Boop Deploys",
        ),
        FeatureSpec(
            "sol_bags_claims",
            "SOL Bags Claims",
            FeatureKind.ALERT,
            Chain.SOLANA,
            TopicFeature.BAGS_CLAIMS,
            "BBB Solana Bags Claims",
        ),
        FeatureSpec(
            "sol_believeapp_deploys",
            "SOL BelieveApp Deploys",
            FeatureKind.DEPLOY_MONITOR,
            Chain.SOLANA,
            TopicFeature.BELIEVEAPP_DEPLOYS,
            "BBB Solana BelieveApp Deploys",
        ),
        FeatureSpec(
            "eth_freshies",
            "ETH Freshies",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.FRESHIES,
            "BBB Ethereum Freshies",
            min_native_amount=0.06,
            max_market_cap_usd=500_000_000,
        ),
        FeatureSpec(
            "eth_big_freshies",
            "ETH Big Freshies",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.BIG_FRESHIES,
            "BBB Ethereum Big Freshies",
            min_native_amount=0.5,
            max_market_cap_usd=500_000_000,
        ),
        FeatureSpec(
            "eth_low_mc_freshies",
            "ETH Low MC Freshies",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.LOW_MC_FRESHIES,
            "BBB Ethereum Low MC Freshies",
            min_native_amount=0.02,
            max_market_cap_usd=500_000,
        ),
        FeatureSpec(
            "eth_dormants",
            "ETH Dormants",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.DORMANTS,
            "BBB Ethereum Dormants",
            min_native_amount=0.06,
            min_inactive_days=14,
        ),
        FeatureSpec(
            "eth_low_mc_dormants",
            "ETH Low MC Dormants",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.LOW_MC_DORMANTS,
            "BBB Ethereum Low MC Dormants",
            min_native_amount=0.02,
            max_market_cap_usd=500_000,
            min_inactive_days=14,
        ),
        FeatureSpec(
            "eth_bundles",
            "ETH Bundles",
            FeatureKind.SUPPLY_ANALYSIS,
            Chain.ETHEREUM,
            TopicFeature.BUNDLES,
            "BBB Ethereum Bundles",
        ),
        FeatureSpec(
            "eth_ens_buys",
            "ETH ENS Buys",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.ENS_BUYS,
            "BBB Ethereum ENS Buys",
        ),
        FeatureSpec(
            "eth_normie_buys",
            "ETH Normie Buys",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.NORMIE_BUYS,
            "BBB Ethereum Normie Buys",
        ),
        FeatureSpec(
            "eth_difference_checker",
            "ETH Difference Checker",
            FeatureKind.WALLET_ANALYSIS,
            Chain.ETHEREUM,
            TopicFeature.DIFFERENCE_CHECKER,
            "BBB Ethereum Difference Checker",
        ),
        FeatureSpec(
            "eth_unique_contracts",
            "ETH Unique Contracts",
            FeatureKind.ALERT,
            Chain.ETHEREUM,
            TopicFeature.UNIQUE_CONTRACTS,
            "BBB Ethereum Unique Contracts",
        ),
        FeatureSpec(
            "eth_pre_approvals",
            "ETH Pre-Approvals",
            FeatureKind.PRE_LIVE,
            Chain.ETHEREUM,
            TopicFeature.PRE_APPROVALS,
            "BBB Ethereum Pre-Approvals",
        ),
        FeatureSpec(
            "eth_launches_tracker",
            "ETH Launches Tracker",
            FeatureKind.DEPLOY_MONITOR,
            Chain.ETHEREUM,
            TopicFeature.LAUNCHES_TRACKER,
            "BBB Ethereum Launches Tracker",
        ),
        FeatureSpec(
            "base_freshies",
            "Base Freshies",
            FeatureKind.ALERT,
            Chain.BASE,
            TopicFeature.FRESHIES,
            "BBB Base Freshies",
            min_native_amount=0.06,
            max_market_cap_usd=25_000_000,
        ),
        FeatureSpec(
            "base_low_mc_freshies",
            "Base Low MC Freshies",
            FeatureKind.ALERT,
            Chain.BASE,
            TopicFeature.LOW_MC_FRESHIES,
            "BBB Base Low MC Freshies",
            min_native_amount=0.02,
            max_market_cap_usd=500_000,
        ),
        FeatureSpec(
            "base_dormants",
            "Base Dormants",
            FeatureKind.ALERT,
            Chain.BASE,
            TopicFeature.DORMANTS,
            "BBB Base Dormants",
            min_native_amount=0.06,
            min_inactive_days=14,
        ),
        FeatureSpec(
            "base_low_mc_dormants",
            "Base Low MC Dormants",
            FeatureKind.ALERT,
            Chain.BASE,
            TopicFeature.LOW_MC_DORMANTS,
            "BBB Base Low MC Dormants",
            min_native_amount=0.02,
            max_market_cap_usd=500_000,
            min_inactive_days=14,
        ),
        FeatureSpec(
            "base_deploys",
            "Base Deploys",
            FeatureKind.DEPLOY_MONITOR,
            Chain.BASE,
            TopicFeature.DEPLOYS,
            "BBB Base Deploys",
            notes="Clanker/Zora deploys with social and recycled username analysis.",
        ),
        FeatureSpec(
            "base_curated_deploys",
            "Base Curated Deploys",
            FeatureKind.DEPLOY_MONITOR,
            Chain.BASE,
            TopicFeature.CURATED_DEPLOYS,
            "BBB Base Curated Deploys",
        ),
        FeatureSpec(
            "base_pre_approvals",
            "Base Pre-Approvals",
            FeatureKind.PRE_LIVE,
            Chain.BASE,
            TopicFeature.PRE_APPROVALS,
            "BBB Base Pre-Approvals",
            min_wallets=5,
        ),
        FeatureSpec(
            "base_ens_buys",
            "Base ENS Buys",
            FeatureKind.ALERT,
            Chain.BASE,
            TopicFeature.ENS_BUYS,
            "BBB Base ENS Buys",
        ),
        FeatureSpec(
            "bnb_freshies",
            "BNB Freshies",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.FRESHIES,
            "BBB BSC Freshies",
            min_native_amount=0.1,
            max_market_cap_usd=500_000_000,
        ),
        FeatureSpec(
            "bnb_big_freshies",
            "BNB Big Freshies",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.BIG_FRESHIES,
            "BBB BSC Big Freshies",
            min_native_amount=0.1,
            max_market_cap_usd=500_000_000,
        ),
        FeatureSpec(
            "bnb_low_mc_freshies",
            "BNB Low MC Freshies",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.LOW_MC_FRESHIES,
            "BBB BSC Low MC Freshies",
            min_native_amount=0.1,
            max_market_cap_usd=500_000,
        ),
        FeatureSpec(
            "bnb_dormants",
            "BNB Dormants",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.DORMANTS,
            "BBB BSC Dormants",
            min_native_amount=0.3,
        ),
        FeatureSpec(
            "bnb_big_dormants",
            "BNB Big Dormants",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.BIG_DORMANTS,
            "BBB BSC Big Dormants",
        ),
        FeatureSpec(
            "bnb_semi_dormants",
            "BNB Semi-Dormants",
            FeatureKind.ALERT,
            Chain.BSC,
            TopicFeature.SEMI_DORMANTS,
            "BBB BSC Semi-Dormants",
        ),
        FeatureSpec(
            "bnb_migrations_tracker",
            "BNB Migrations Tracker",
            FeatureKind.PRE_LIVE,
            Chain.BSC,
            TopicFeature.MIGRATIONS_TRACKER,
            "BBB BSC Migrations Tracker",
        ),
        FeatureSpec(
            "bnb_bundles",
            "BNB Bundles",
            FeatureKind.SUPPLY_ANALYSIS,
            Chain.BSC,
            TopicFeature.BUNDLES,
            "RAVNView BSC bundle scanner",
        ),
    ]
