"""
Trench Tool V1 - Router Detector
Identifies which trading bot/router was used for a transaction.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class RouterInfo:
    """Information about a detected trading router."""
    name: str
    emoji: str
    program_id: str


# Known Solana trading bot router program IDs
ROUTERS = {
    # Axiom
    "AXiomxV9ACRG1dXDHEfF9RQVDxWrtkMJ8JxAqYaRvjsW": RouterInfo(
        name="Axiom",
        emoji="🔳",
        program_id="AXiomxV9ACRG1dXDHEfF9RQVDxWrtkMJ8JxAqYaRvjsW"
    ),
    
    # BananaGun
    "BANANAjs7FJiPQqXit9LXCHPLeTqsX6RMDY8fVGPpump": RouterInfo(
        name="BananaGun",
        emoji="🍌",
        program_id="BANANAjs7FJiPQqXit9LXCHPLeTqsX6RMDY8fVGPpump"
    ),
    
    # Maestro
    "MAESTRoK3J8SWDoFJmoeQJYvvmE4DUpUc9mRWPzJ7hh": RouterInfo(
        name="Maestro",
        emoji="Ⓜ️",
        program_id="MAESTRoK3J8SWDoFJmoeQJYvvmE4DUpUc9mRWPzJ7hh"
    ),
    
    # Trojan
    "TROJANxHLe8DRc9rHnYeFvNqPRGK6B9AGKK6Ts8pump": RouterInfo(
        name="Trojan",
        emoji="🔱",
        program_id="TROJANxHLe8DRc9rHnYeFvNqPRGK6B9AGKK6Ts8pump"
    ),
    
    # Bloom
    "BLooMbSK2F8V5HxELEKNTBPLfBn9iKc2HKxMTSpTpump": RouterInfo(
        name="Bloom",
        emoji="🌸",
        program_id="BLooMbSK2F5HxELEKNTBPLfBn9iKc2HKxMTSpTpump"
    ),
    
    # Photon
    "PHoToN7Y1CxgF8qFVQPYNPY8DZ7EzbS7LVNW7pPpump": RouterInfo(
        name="Photon",
        emoji="📸",
        program_id="PHoToN7Y1CxgF8qFVQPYNPY8DZ7EzbS7LVNW7pPpump"
    ),
    
    # Padre
    "PADRERoKnqcTPVE8HfUJemWdqfvB6vKGEM9oBWRpump": RouterInfo(
        name="Padre",
        emoji="🏮",
        program_id="PADRERoKnqcTPVE8HfUJemWdqfvB6vKGEM9oBWRpump"
    ),
    
    # BullX/Nova
    "NoVAxHC5jvTnJSbrMBheVkLYhq46dZdJpxTzS3DXpump": RouterInfo(
        name="Nova/BullX",
        emoji="♋️",
        program_id="NoVAxHC5jvTnJSbrMBheVkLYhq46dZdJpxTzS3DXpump"
    ),
    
    # Mintech
    "MiNTECHB5f5gu9LnHJVNM2UZg3muK79PBD1Dphd3PfV": RouterInfo(
        name="Mintech",
        emoji="📱",
        program_id="MiNTECHB5f5gu9LnHJVNM2UZg3muK79PBD1Dphd3PfV"
    ),
    
    # Bonk Bot
    "BoNkBoTmemesMemeSmeme4MemeSMEMESmemepump": RouterInfo(
        name="Bonk Bot",
        emoji="🐕",
        program_id="BoNkBoTmemesMemeSmeme4MemeSMEMESmemepump"
    ),
}


def detect_router(program_ids: list[str]) -> Optional[RouterInfo]:
    """
    Detect which trading router was used based on program IDs.
    
    Args:
        program_ids: List of program IDs from the transaction
        
    Returns:
        RouterInfo if detected, None otherwise
    """
    for program_id in program_ids:
        if program_id in ROUTERS:
            return ROUTERS[program_id]
    return None


def get_router_emoji(program_ids: list[str]) -> str:
    """Get just the emoji for the router."""
    info = detect_router(program_ids)
    return info.emoji if info else ""


def get_router_name(program_ids: list[str]) -> str:
    """Get the router name."""
    info = detect_router(program_ids)
    return info.name if info else ""


# All known router program IDs
ROUTER_PROGRAM_IDS = set(ROUTERS.keys())


def is_bot_transaction(program_ids: list[str]) -> bool:
    """Check if transaction was made through a known trading bot."""
    return any(pid in ROUTER_PROGRAM_IDS for pid in program_ids)
