"""
Trench Tool V1 - Launchpad Detector
Identifies which DEX/launchpad a token was launched on.
"""

from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class LaunchpadInfo:
    """Information about a detected launchpad."""
    name: str
    emoji: str
    program_id: str


# Known Solana launchpad/DEX program IDs
LAUNCHPADS = {
    # Pump.fun
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": LaunchpadInfo(
        name="Pump.fun",
        emoji="💊",
        program_id="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    ),
    
    # Meteora
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": LaunchpadInfo(
        name="Meteora",
        emoji="☄️",
        program_id="LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
    ),
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": LaunchpadInfo(
        name="Meteora DLMM",
        emoji="☄️",
        program_id="Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB"
    ),
    
    # Raydium
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": LaunchpadInfo(
        name="Raydium AMM",
        emoji="®️",
        program_id="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    ),
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": LaunchpadInfo(
        name="Raydium CLMM",
        emoji="®️💧",
        program_id="CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    ),
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": LaunchpadInfo(
        name="Raydium CPMM",
        emoji="®️",
        program_id="CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
    ),
    
    # Orca
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": LaunchpadInfo(
        name="Orca Whirlpool",
        emoji="🐋",
        program_id="whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    ),
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": LaunchpadInfo(
        name="Orca",
        emoji="🐋",
        program_id="9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP"
    ),
    
    # Bonk
    "BSwp6bEBihVLdqJRKGgzjcGLHkcTuzmSo1TQkHepzH8p": LaunchpadInfo(
        name="Bonk Launchpad",
        emoji="🐕",
        program_id="BSwp6bEBihVLdqJRKGgzjcGLHkcTuzmSo1TQkHepzH8p"
    ),
    
    # Moonshot
    "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG": LaunchpadInfo(
        name="Moonshot",
        emoji="🌙",
        program_id="MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"
    ),
    
    # Jupiter
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": LaunchpadInfo(
        name="Jupiter V6",
        emoji="🪐",
        program_id="JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    ),
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": LaunchpadInfo(
        name="Jupiter V4",
        emoji="🪐",
        program_id="JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB"
    ),
}


def detect_launchpad(program_ids: list[str]) -> Optional[LaunchpadInfo]:
    """
    Detect which launchpad was used based on program IDs in transaction.
    
    Args:
        program_ids: List of program IDs from the transaction
        
    Returns:
        LaunchpadInfo if detected, None otherwise
    """
    for program_id in program_ids:
        if program_id in LAUNCHPADS:
            return LAUNCHPADS[program_id]
    return None


def get_launchpad_emoji(program_ids: list[str]) -> str:
    """Get just the emoji for the launchpad."""
    info = detect_launchpad(program_ids)
    return info.emoji if info else ""


def get_launchpad_name(program_ids: list[str]) -> str:
    """Get the launchpad name."""
    info = detect_launchpad(program_ids)
    return info.name if info else "Unknown"


# All known DEX program IDs for filtering
DEX_PROGRAM_IDS = set(LAUNCHPADS.keys())


def is_dex_transaction(program_ids: list[str]) -> bool:
    """Check if transaction involves a known DEX."""
    return any(pid in DEX_PROGRAM_IDS for pid in program_ids)
