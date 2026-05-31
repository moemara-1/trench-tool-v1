"""Telegram topic registry for V2 alert routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from trench_v2.config import V2Settings
from trench_v2.core.models import Chain


class TopicFeature(str, Enum):
    """Doc-backed alert/command surfaces that can route to Telegram topics."""

    SCAN = "scan"
    ANALYZE = "analyze"
    TRACK = "track"
    OG = "og"
    SIMULATE = "simulate"
    FRESHIES = "freshies"
    BIG_FRESHIES = "big_freshies"
    LOW_MC_FRESHIES = "low_mc_freshies"
    FRESHIES_SELLS = "freshies_sells"
    DORMANTS = "dormants"
    BIG_DORMANTS = "big_dormants"
    LOW_MC_DORMANTS = "low_mc_dormants"
    SEMI_DORMANTS = "semi_dormants"
    SEMI_DORMANTS_SELLS = "semi_dormants_sells"
    BUNDLES = "bundles"
    PATTERNS = "patterns"
    WIZARD = "wizard"
    PRE_MIGRATION_DORMANTS = "pre_migration_dormants"
    FRESHIES_INFLOW = "freshies_inflow"
    FRESHIES_SPIKE = "freshies_spike"
    VANISH_SELLS = "vanish_sells"
    MIGRATIONS_TRACKER = "migrations_tracker"
    OLD_MIGRATIONS = "old_migrations"
    DORMANT_DEPLOYS = "dormant_deploys"
    JUPITER_DCA = "jupiter_dca"
    LIQUIDITY_INFLOWS = "liquidity_inflows"
    BOOP_DEPLOYS = "boop_deploys"
    BAGS_CLAIMS = "bags_claims"
    BELIEVEAPP_DEPLOYS = "believeapp_deploys"
    DEPLOYS = "deploys"
    CURATED_DEPLOYS = "curated_deploys"
    PRE_APPROVALS = "pre_approvals"
    ENS_BUYS = "ens_buys"
    NORMIE_BUYS = "normie_buys"
    DIFFERENCE_CHECKER = "difference_checker"
    UNIQUE_CONTRACTS = "unique_contracts"
    LAUNCHES_TRACKER = "launches_tracker"
    SOCIALS = "socials"
    DEV_HELD = "dev_held"
    GOOD_CREATOR = "good_creator"
    STRONG_LAUNCH = "strong_launch"
    STRONGFLOOR = "strongfloor"
    STREAMFLOW = "streamflow"
    VANISH = "vanish"
    SNS = "sns"
    BEST_WALLETS_WEEK = "best_wallets_week"
    BEST_WALLETS_MONTH = "best_wallets_month"
    BEST_WALLETS_YEAR = "best_wallets_year"
    BEST_SIGNALS = "best_signals"
    FEEDBACK = "feedback"


@dataclass(frozen=True, slots=True)
class TopicTarget:
    chain: Chain | None
    feature: TopicFeature
    title: str
    env_key: str


def topic_env_key(chain: Chain, feature: TopicFeature) -> str:
    chain_slug = "ETH" if chain is Chain.ETHEREUM else "BNB" if chain is Chain.BSC else chain.label
    feature_slug = feature.value.upper()
    return f"TELEGRAM_{chain_slug}_{feature_slug}_TOPIC_ID"


def build_default_topic_plan() -> tuple[TopicTarget, ...]:
    targets: list[TopicTarget] = []

    def add(chain: Chain, feature: TopicFeature, title: str, env_key: str | None = None) -> None:
        targets.append(
            TopicTarget(
                chain=chain,
                feature=feature,
                title=title,
                env_key=env_key or topic_env_key(chain, feature),
            )
        )

    def add_global(feature: TopicFeature, title: str, env_key: str) -> None:
        targets.append(
            TopicTarget(
                chain=None,
                feature=feature,
                title=title,
                env_key=env_key,
            )
        )

    # Only include topics with a live producer. The feature catalog can keep
    # docs-backed future surfaces, but Telegram should not expose dead rooms.
    for feature, title in [
        (TopicFeature.FRESHIES, "Freshies (SOL)"),
        (TopicFeature.DORMANTS, "Dormant (SOL)"),
        (TopicFeature.MIGRATIONS_TRACKER, "Migrations Tracker (SOL)"),
        (TopicFeature.PATTERNS, "Patterns (SOL)"),
        (TopicFeature.WIZARD, "Freshies Wizard"),
    ]:
        add(Chain.SOLANA, feature, title)

    for feature, title in [
        (TopicFeature.FRESHIES, "ETH Freshies"),
        (TopicFeature.BIG_FRESHIES, "ETH Big Freshies"),
        (TopicFeature.LOW_MC_FRESHIES, "ETH Low MC Freshies"),
    ]:
        add(Chain.ETHEREUM, feature, title)

    for feature, title in [
        (TopicFeature.FRESHIES, "Base Freshies"),
        (TopicFeature.LOW_MC_FRESHIES, "Base Low MC Freshies"),
        (TopicFeature.DEPLOYS, "Base Deploys"),
    ]:
        add(Chain.BASE, feature, title)

    for feature, title in [
        (TopicFeature.FRESHIES, "BNB Freshies"),
        (TopicFeature.BIG_FRESHIES, "BNB Big Freshies"),
        (TopicFeature.LOW_MC_FRESHIES, "BNB Low MC Freshies"),
    ]:
        add(Chain.BSC, feature, title)

    add_global(TopicFeature.BEST_SIGNALS, "Best Signals", "TELEGRAM_BEST_SIGNALS_TOPIC_ID")
    add_global(TopicFeature.BEST_WALLETS_WEEK, "Best Wallets Week", "TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID")
    add_global(TopicFeature.BEST_WALLETS_MONTH, "Best Wallets Month", "TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID")
    add_global(TopicFeature.BEST_WALLETS_YEAR, "Best Wallets Year", "TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID")

    return tuple(targets)


def working_topic_ids(settings: V2Settings) -> dict[str, int]:
    topics = settings.telegram_topic_ids or {}
    return {key: value for key, value in topics.items() if value > 0}
