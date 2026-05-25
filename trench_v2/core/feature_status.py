"""Implementation readiness metadata for docs-backed V2 features."""

from __future__ import annotations

from dataclasses import dataclass

from trench_v2.config import V2Settings
from trench_v2.core.feature_catalog import FeatureCatalog, FeatureKind
from trench_v2.core.models import Chain
from trench_v2.telegram.topics import build_default_topic_plan, topic_env_key, working_topic_ids


@dataclass(frozen=True, slots=True)
class FeatureReadiness:
    status: str
    blocked_on: list[str]


class FeatureReadinessService:
    """Explain whether a feature is live, provider-ready, or key/source gated."""

    _UNCONFIRMED_SOLANA_PROTOCOLS = {
        "sol_boop_deploys",
        "sol_bags_claims",
        "sol_believeapp_deploys",
    }
    _EVM_LOG_FEATURES = {
        "eth_pre_approvals",
        "base_pre_approvals",
        "eth_launches_tracker",
        "bnb_migrations_tracker",
    }
    _EVM_WALLET_FEATURES = {
        "eth_dormants",
        "eth_low_mc_dormants",
        "eth_ens_buys",
        "eth_normie_buys",
        "eth_difference_checker",
        "eth_unique_contracts",
        "base_dormants",
        "base_low_mc_dormants",
        "base_ens_buys",
        "bnb_dormants",
        "bnb_big_dormants",
        "bnb_semi_dormants",
    }
    _HOLDER_FEATURES = {
        "ravn_bundle_supply",
        "eth_bundles",
        "bnb_bundles",
        "sol_bundles",
    }

    def __init__(self, settings: V2Settings, catalog: FeatureCatalog | None = None):
        self.settings = settings
        self.catalog = catalog or FeatureCatalog.default()
        self._active_topic_keys = set(working_topic_ids(settings))
        self._live_topic_keys = {target.env_key for target in build_default_topic_plan()}

    def for_feature(self, feature_id: str) -> FeatureReadiness:
        spec = self.catalog.get(feature_id)
        if spec.chain and topic_env_key(spec.chain, spec.topic_feature) in (
            self._active_topic_keys | self._live_topic_keys
        ):
            return FeatureReadiness(status="live_producer", blocked_on=[])

        if feature_id in self._UNCONFIRMED_SOLANA_PROTOCOLS:
            return FeatureReadiness(
                status="blocked_external_source",
                blocked_on=["official protocol program/API source"],
            )

        if feature_id in self._HOLDER_FEATURES:
            if self.settings.moralis_api_key or self.settings.etherscan_api_key:
                return FeatureReadiness(status="provider_ready", blocked_on=[])
            return FeatureReadiness(
                status="needs_api_key",
                blocked_on=["MORALIS_API_KEY or ETHERSCAN_API_KEY"],
            )

        if feature_id in self._EVM_LOG_FEATURES:
            if self.settings.etherscan_api_key or self._has_evm_rpc(spec.chain):
                return FeatureReadiness(status="provider_ready", blocked_on=[])
            return FeatureReadiness(
                status="needs_api_key",
                blocked_on=["ALCHEMY_API_KEY or ETHERSCAN_API_KEY"],
            )

        if feature_id in self._EVM_WALLET_FEATURES:
            if self.settings.etherscan_api_key or self._has_evm_rpc(spec.chain):
                return FeatureReadiness(status="provider_ready", blocked_on=[])
            return FeatureReadiness(
                status="needs_api_key",
                blocked_on=["ALCHEMY_API_KEY or ETHERSCAN_API_KEY"],
            )

        if spec.chain is Chain.SOLANA:
            if self.settings.helius_api_keys or self.settings.solana_rpc_url:
                return FeatureReadiness(status="provider_ready", blocked_on=[])
            return FeatureReadiness(status="needs_api_key", blocked_on=["HELIUS_API_KEYS"])

        if spec.kind is FeatureKind.COMMAND or feature_id in {
            "ravnview_track",
            "ravnview_simulate",
        }:
            status = "provider_ready" if self.settings.command_providers_enabled else "contract_ready"
            return FeatureReadiness(status=status, blocked_on=[])

        if spec.chain and topic_env_key(spec.chain, spec.topic_feature) in self._live_topic_keys:
            return FeatureReadiness(status="contract_ready", blocked_on=[])

        return FeatureReadiness(status="planned", blocked_on=[])

    def _has_evm_rpc(self, chain: Chain | None) -> bool:
        if chain is None:
            return bool(
                self.settings.rpc_url_for(Chain.ETHEREUM)
                or self.settings.rpc_url_for(Chain.BASE)
                or self.settings.rpc_url_for(Chain.BSC)
            )
        if chain is Chain.SOLANA:
            return False
        return self.settings.rpc_url_for(chain) is not None
