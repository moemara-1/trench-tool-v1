"""
Trench Tool V1 - Configuration Module
Loads environment variables and provides typed settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Solana RPC
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="Solana RPC endpoint"
    )
    solana_ws_url: str = Field(
        default="wss://api.mainnet-beta.solana.com",
        description="Solana WebSocket endpoint"
    )
    
    # Helius RPC Keys (comma-separated for multi-RPC rotation)
    helius_api_keys_raw: str = Field(
        default="",
        alias="helius_api_keys",
        description="Comma-separated Helius API keys for RPC rotation"
    )
    
    @property
    def helius_api_keys(self) -> list:
        """Parse comma-separated API keys into a list."""
        if not self.helius_api_keys_raw:
            return []
        return [k.strip() for k in self.helius_api_keys_raw.split(',') if k.strip()]
    
    # Telegram Bot
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot API token"
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID for alerts"
    )
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/trench",
        description="PostgreSQL connection string"
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string"
    )
    
    # Alert Settings
    alert_cooldown_seconds: int = Field(
        default=30,
        description="Cooldown between duplicate alerts"
    )
    min_transaction_sol: float = Field(
        default=0.47,
        description="Minimum transaction size to track"
    )
    min_market_cap: float = Field(
        default=15000,
        description="Minimum market cap to alert (filter out micro caps)"
    )
    
    # Fresh Wallet Thresholds
    fresh_wallet_max_age_days: int = Field(
        default=7,
        description="Max wallet age to be considered 'fresh'"
    )
    dormant_wallet_min_inactive_days: int = Field(
        default=30,
        description="Min inactive days to be considered 'dormant'"
    )
    
    # Whale Thresholds
    whale_threshold_sol: float = Field(
        default=15.0,
        description="Transaction size for whale emoji 🐳"
    )
    dolphin_threshold_sol: float = Field(
        default=5.0,
        description="Transaction size for dolphin emoji 🐬"
    )
    
    # Dormant Wallet Settings
    min_dormant_sol: float = Field(
        default=3.0,
        description="Minimum SOL for Dormants alert"
    )
    dormant_min_days: int = Field(
        default=4,
        description="Minimum days inactive to be 'dormant'"
    )
    dormant_old_days: int = Field(
        default=8,
        description="Days inactive for 'old dormant' 👴🏻"
    )
    
    # Separate Telegram Channels
    telegram_dormants_chat_id: str = Field(
        default="",
        description="Telegram chat ID for Dormants alerts"
    )
    
    # Telegram Topic IDs (for Forum groups)
    telegram_freshies_topic_id: int = Field(
        default=0,
        description="Topic ID for Freshies alerts (0 = disabled)"
    )
    telegram_dormants_topic_id: int = Field(
        default=0,
        description="Topic ID for Dormants alerts (0 = disabled)"
    )
    telegram_sns_topic_id: int = Field(
        default=0,
        description="Topic ID for SNS Buys alerts (0 = disabled)"
    )
    telegram_vanish_topic_id: int = Field(
        default=0,
        description="Topic ID for Vanish Buys alerts (0 = disabled)"
    )
    telegram_bundles_topic_id: int = Field(
        default=0,
        description="Topic ID for Bundle alerts (0 = disabled)"
    )
    telegram_patterns_topic_id: int = Field(
        default=0,
        description="Topic ID for Pattern alerts (0 = disabled)"
    )
    telegram_wizard_topic_id: int = Field(
        default=0,
        description="Topic ID for Wizard alerts (0 = disabled)"
    )
    
    # New Tracker Topic IDs
    telegram_late_migration_topic_id: int = Field(
        default=0,
        description="Topic ID for Late Migration alerts"
    )
    telegram_streamflow_topic_id: int = Field(
        default=0,
        description="Topic ID for Streamflow Lock alerts"
    )
    telegram_dev_held_topic_id: int = Field(
        default=0,
        description="Topic ID for Dev Held alerts"
    )
    telegram_good_creator_topic_id: int = Field(
        default=0,
        description="Topic ID for Good Creator alerts"
    )
    telegram_socials_topic_id: int = Field(
        default=0,
        description="Topic ID for Socials Check alerts"
    )
    telegram_strong_launch_topic_id: int = Field(
        default=1332,
        description="Topic ID for Strong Launch alerts"
    )
    telegram_strongfloor_topic_id: int = Field(
        default=0,
        description="Topic ID for Strongfloor alerts"
    )
    telegram_feedback_topic_id: int = Field(
        default=0,
        description="Topic ID for Feedback/Startup messages"
    )
    
    # Token Verification Settings
    min_liquidity_usd: float = Field(
        default=500.0,
        description="Minimum liquidity in USD for pattern tracking"
    )
    min_market_cap_patterns: float = Field(
        default=10000.0,
        description="Minimum market cap in USD for pattern tracking"
    )
    
    # AI/LLM Configuration
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key (legacy)"
    )
    gemini_api_keys: str = Field(
        default="",
        description="Comma-separated Gemini API keys for rotation"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export singleton
settings = get_settings()
