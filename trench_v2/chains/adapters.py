"""Chain address parsing and adapter registry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from trench_v2.core.models import Chain


EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass(frozen=True, slots=True)
class ChainAdapter:
    chain: Chain

    def accepts(self, address: str) -> bool:
        if self.chain is Chain.SOLANA:
            return bool(SOLANA_ADDRESS_RE.match(address))
        return bool(EVM_ADDRESS_RE.match(address))


class ChainAdapterRegistry:
    """Resolves chain hints and token address formats."""

    def __init__(self, adapters: Iterable[ChainAdapter] | None = None):
        self._adapters = list(adapters or [ChainAdapter(chain) for chain in Chain])

    def resolve(self, address: str, hint: Chain | str | None = None) -> Chain:
        if isinstance(hint, Chain):
            return hint
        if isinstance(hint, str) and hint.strip():
            return Chain.from_hint(hint)

        matches = [adapter.chain for adapter in self._adapters if adapter.accepts(address)]
        if not matches:
            raise ValueError(f"Cannot infer chain for address: {address}")
        if len(matches) > 1:
            # EVM addresses are valid on ETH/BSC/Base. Default to ETH unless a
            # command or API caller provides an explicit chain hint.
            return Chain.ETHEREUM
        return matches[0]


default_registry = ChainAdapterRegistry()

