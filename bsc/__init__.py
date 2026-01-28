"""
BSC Bot Package
Monitors BSC chain for fresh wallet and dormant wallet activity.
"""

from bsc.bsc_config import bsc_settings, get_bsc_settings
from bsc.bsc_listener import get_bsc_listener
from bsc.bsc_telegram_bot import get_bsc_telegram_bot
from bsc.bsc_channel_router import get_bsc_channel_router
from bsc.bsc_wallet_classifier import get_bsc_wallet_classifier
from bsc.bsc_tx_tracker import get_bsc_tx_tracker
from bsc.bsc_api_clients import get_bsc_token_fetcher, get_bscscan_client

__all__ = [
    "bsc_settings",
    "get_bsc_settings",
    "get_bsc_listener",
    "get_bsc_telegram_bot",
    "get_bsc_channel_router",
    "get_bsc_wallet_classifier",
    "get_bsc_tx_tracker",
    "get_bsc_token_fetcher",
    "get_bscscan_client",
]
