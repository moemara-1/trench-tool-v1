"""
BSC Bot Configuration Module
Loads environment variables and provides typed settings for BSC chain.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class BSCSettings(BaseSettings):
    """BSC-specific settings loaded from environment variables."""
    
    # BSC RPC
    bsc_rpc_url: str = Field(
        default="https://bsc-dataseed.binance.org",
        description="BSC RPC endpoint"
    )
    bsc_ws_url: str = Field(
        default="wss://bsc-ws-node.nariox.org:443",
        description="BSC WebSocket endpoint"
    )
    
    # BscScan API
    bscscan_api_key: str = Field(
        default="",
        description="BscScan API key"
    )
    
    # Telegram Bot (shared with Solana or separate)
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot API token"
    )
    telegram_bsc_chat_id: str = Field(
        default="-1003509316792",
        description="Telegram chat ID for BSC alerts"
    )
    
    # Telegram Topic IDs for BSC channels
    telegram_bsc_freshies_topic_id: int = Field(
        default=1091,
        description="Topic ID for BSC Freshies alerts"
    )
    telegram_bsc_dormants_topic_id: int = Field(
        default=1101,
        description="Topic ID for BSC Dormants alerts"
    )
    telegram_bsc_big_freshies_topic_id: int = Field(
        default=0,
        description="Topic ID for BSC Big Freshies alerts (0 = use freshies)"
    )
    telegram_bsc_lowmc_topic_id: int = Field(
        default=0,
        description="Topic ID for BSC Low MC Freshies alerts (0 = use freshies)"
    )
    telegram_bsc_semidormants_topic_id: int = Field(
        default=0,
        description="Topic ID for BSC Semi-Dormants alerts (0 = use dormants)"
    )
    
    # Transaction Thresholds
    min_transaction_bnb: float = Field(
        default=0.1,
        description="Minimum transaction size to track (BNB)"
    )
    min_dormant_bnb: float = Field(
        default=0.3,
        description="Minimum BNB for Dormants alert"
    )
    
    # Whale/Dolphin Thresholds
    whale_threshold_bnb: float = Field(
        default=3.0,
        description="Transaction size for whale emoji 🐳 (BNB)"
    )
    dolphin_threshold_bnb: float = Field(
        default=1.0,
        description="Transaction size for dolphin emoji 🐬 (BNB)"
    )
    whale_threshold_usd: float = Field(
        default=3000.0,
        description="Transaction size for whale emoji 🐳 (USD)"
    )
    dolphin_threshold_usd: float = Field(
        default=1000.0,
        description="Transaction size for dolphin emoji 🐬 (USD)"
    )
    
    # Fresh Wallet Thresholds
    fresh_wallet_max_age_days: int = Field(
        default=7,
        description="Max wallet age to be considered 'fresh'"
    )
    fresh_wallet_max_tx_count: int = Field(
        default=50,
        description="Max tx count to be considered 'fresh'"
    )
    
    # Dormant Wallet Settings
    dormant_min_days: int = Field(
        default=7,
        description="Minimum days inactive to be 'dormant' (🕰️)"
    )
    dormant_old_days: int = Field(
        default=12,
        description="Days inactive for 'old dormant' (👴🏻)"
    )
    semidormant_min_days: int = Field(
        default=3,
        description="Minimum days inactive to be 'semi-dormant'"
    )
    semidormant_max_days: int = Field(
        default=6,
        description="Maximum days inactive for 'semi-dormant'"
    )
    
    # Market Cap Thresholds
    max_market_cap: float = Field(
        default=500_000_000,
        description="Maximum market cap for Freshies alerts (500M)"
    )
    low_mc_threshold: float = Field(
        default=500_000,
        description="Maximum market cap for Low MC Freshies (500K)"
    )
    
    # Alert Settings
    alert_cooldown_seconds: int = Field(
        default=30,
        description="Cooldown between duplicate alerts"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        env_prefix = "BSC_"  # Environment variables prefixed with BSC_


@lru_cache()
def get_bsc_settings() -> BSCSettings:
    """Get cached BSC settings instance."""
    return BSCSettings()


# Export singleton
bsc_settings = get_bsc_settings()
