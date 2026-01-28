"""
Token Verification Service

Validates tokens before pattern detection to filter out scams/rugs.
Only allows tokens from verified launchpads with sufficient liquidity/market cap.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Set

logger = logging.getLogger(__name__)


# Verified launchpads and DEXes (excludes Raydium - too many scams)
VERIFIED_LAUNCHPADS: Set[str] = {
    # pump.fun
    "pump.fun",
    "pumpfun",
    
    # Believe
    "believe",
    "launchcoin",
    
    # Bags
    "bags",
    
    # Bonk / Letsbonk
    "bonk",
    "letsbonk",
    
    # Boop
    "boop",
    
    # Moonshot
    "moonshot",
    
    # Orca
    "orca",
    
    # Meteora
    "meteora",
    
    # Jupiter (aggregator, not launchpad but trusted)
    "jupiter",
    
    # Sugar
    "sugar",
    
    # Other known launchpads
    "virtuals",
    "launch",
    
    # Raydium (many legit tokens launch here)
    "raydium",
}

# DEX IDs from DexScreener that are verified
VERIFIED_DEX_IDS: Set[str] = {
    # pump.fun variants
    "pumpfun",
    "pump",
    
    # Orca
    "orca",
    
    # Meteora
    "meteora",
    
    # Jupiter
    "jupiter",
    
    # Moonshot
    "moonshot",
    
    # Lifinity
    "lifinity",
    
    # Raydium (allowed - has many legit tokens)
    "raydium",
    "raydium_clmm",
    "raydium_cpmm",
    
    # NOTE: We now allow Raydium since many legitimate tokens launch there
}

# Program IDs of verified launchpads
VERIFIED_PROGRAM_IDS: Set[str] = {
    # pump.fun
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    
    # Moonshot
    "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG",
    
    # Orca
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",
    
    # Meteora
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",
    
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",
    
    # Bonk / Letsbonk
    "BSwp6bEBihVLdqJRKGgzjcGLHkcTuzmSo1TQkHepzH8p",
    
    # Lifinity
    "EewxydAPCCVuNEyrVN68PuSYdQ7wKn27V9Gjeoi8dy3S",
    
    # Phoenix
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY",
    
    # Raydium (all variants now allowed)
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",  # Raydium CLMM
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",  # Raydium CPMM
}


@dataclass
class TokenVerification:
    """Result of token verification."""
    is_verified: bool
    rejection_reason: Optional[str] = None
    dex_name: str = ""
    liquidity_usd: float = 0.0
    market_cap: float = 0.0
    is_from_launchpad: bool = False


class TokenVerifier:
    """Verifies tokens before allowing pattern tracking."""
    
    # Thresholds
    MIN_LIQUIDITY_USD: float = 500.0  # $500 minimum liquidity
    MIN_MARKET_CAP_USD: float = 10_000.0  # $10k minimum market cap
    
    def __init__(self):
        self._verified_cache: dict[str, TokenVerification] = {}
        self._rejection_count: int = 0
        self._approval_count: int = 0
    
    def verify_from_data(
        self,
        token_address: str,
        dex_name: str = "",
        liquidity_usd: float = 0.0,
        market_cap: float = 0.0,
        program_ids: list = None,
    ) -> TokenVerification:
        """
        Verify a token using available data.
        
        Args:
            token_address: Token contract address
            dex_name: DEX name from DexScreener
            liquidity_usd: Token liquidity in USD
            market_cap: Token market cap in USD
            program_ids: Program IDs from transaction
        
        Returns:
            TokenVerification result
        """
        program_ids = program_ids or []
        
        # Check cache
        if token_address in self._verified_cache:
            return self._verified_cache[token_address]
        
        # Check 1: Is it from a verified launchpad/DEX?
        is_from_launchpad = self._is_verified_source(dex_name, program_ids)
        
        if not is_from_launchpad:
            result = TokenVerification(
                is_verified=False,
                rejection_reason=f"Not from verified launchpad (dex: {dex_name})",
                dex_name=dex_name,
                liquidity_usd=liquidity_usd,
                market_cap=market_cap,
                is_from_launchpad=False,
            )
            self._cache_rejection(token_address, result)
            return result
        
        # Check 2: Minimum liquidity
        if liquidity_usd < self.MIN_LIQUIDITY_USD:
            result = TokenVerification(
                is_verified=False,
                rejection_reason=f"Low liquidity: ${liquidity_usd:.0f} < ${self.MIN_LIQUIDITY_USD:.0f}",
                dex_name=dex_name,
                liquidity_usd=liquidity_usd,
                market_cap=market_cap,
                is_from_launchpad=True,
            )
            self._cache_rejection(token_address, result)
            return result
        
        # Check 3: Minimum market cap
        if market_cap < self.MIN_MARKET_CAP_USD:
            result = TokenVerification(
                is_verified=False,
                rejection_reason=f"Low market cap: ${market_cap:.0f} < ${self.MIN_MARKET_CAP_USD:.0f}",
                dex_name=dex_name,
                liquidity_usd=liquidity_usd,
                market_cap=market_cap,
                is_from_launchpad=True,
            )
            self._cache_rejection(token_address, result)
            return result
        
        # All checks passed!
        result = TokenVerification(
            is_verified=True,
            dex_name=dex_name,
            liquidity_usd=liquidity_usd,
            market_cap=market_cap,
            is_from_launchpad=True,
        )
        self._verified_cache[token_address] = result
        self._approval_count += 1
        
        logger.debug(f"✅ Token verified: {token_address[:8]} | {dex_name} | Liq: ${liquidity_usd:.0f} | MC: ${market_cap:.0f}")
        return result
    
    def _is_verified_source(self, dex_name: str, program_ids: list) -> bool:
        """Check if token is from a verified launchpad/DEX.
        
        Primary check: program IDs (most reliable)
        Secondary check: DEX name from DexScreener
        Block: Raydium and unknown sources with no verified program ID
        """
        dex_lower = dex_name.lower().strip()
        
        # NOTE: Removed Raydium rejection - many legit tokens launch there
        # if "raydium" in dex_lower:
        #     return False
        
        # PRIMARY CHECK: Program IDs are most reliable
        # If transaction has a verified program ID, allow it
        for pid in program_ids:
            if pid in VERIFIED_PROGRAM_IDS:
                return True
        
        # SECONDARY CHECK: DEX name from DexScreener
        if dex_lower:
            # Check if DEX name matches verified list
            for verified in VERIFIED_LAUNCHPADS:
                if verified in dex_lower:
                    return True
            
            for verified in VERIFIED_DEX_IDS:
                if verified in dex_lower:
                    return True
        
        # No verified source found
        return False
    
    def _cache_rejection(self, token_address: str, result: TokenVerification) -> None:
        """Cache rejection and log."""
        self._verified_cache[token_address] = result
        self._rejection_count += 1
        logger.debug(f"⛔ Token rejected: {token_address[:8]} | {result.rejection_reason}")
    
    def is_verified(self, token_address: str) -> bool:
        """Quick check if token is already verified."""
        cached = self._verified_cache.get(token_address)
        return cached.is_verified if cached else False
    
    def get_stats(self) -> dict:
        """Get verification statistics."""
        return {
            "verified": self._approval_count,
            "rejected": self._rejection_count,
            "cached": len(self._verified_cache),
        }
    
    def clear_cache(self) -> None:
        """Clear verification cache."""
        self._verified_cache.clear()


# Singleton
_token_verifier: Optional[TokenVerifier] = None


def get_token_verifier() -> TokenVerifier:
    """Get singleton token verifier."""
    global _token_verifier
    if _token_verifier is None:
        _token_verifier = TokenVerifier()
    return _token_verifier
