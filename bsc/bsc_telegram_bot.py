"""
BSC Telegram Bot
Formats and sends BSC alerts to Telegram.
"""

import asyncio
import logging
from typing import Optional
from telegram import Bot
from telegram.constants import ParseMode

from bsc.bsc_config import bsc_settings
from bsc.bsc_channel_router import BSCChannelClassification, BSCChannel
from bsc.bsc_tx_tracker import TokenStats
from bsc.bsc_api_clients import BSCTokenData

logger = logging.getLogger(__name__)


class BSCTelegramBot:
    """Sends BSC alerts to Telegram."""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or bsc_settings.telegram_bot_token
        self.chat_id = chat_id or bsc_settings.telegram_bsc_chat_id
        self._bot: Optional[Bot] = None
    
    def _get_bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self.bot_token)
        return self._bot
    
    async def send_alert(self, message: str, topic_id: int = 0):
        """Send alert to Telegram."""
        try:
            bot = self._get_bot()
            
            kwargs = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": ParseMode.HTML,
                "disable_web_page_preview": True,
            }
            
            if topic_id > 0:
                kwargs["message_thread_id"] = topic_id
            
            await bot.send_message(**kwargs)
            logger.info(f"📤 BSC alert sent to topic {topic_id}")
            
        except Exception as e:
            logger.error(f"Failed to send BSC alert: {e}")
    
    def format_freshies_alert(
        self,
        token: BSCTokenData,
        classification: BSCChannelClassification,
        stats: TokenStats,
        wallet_classification,
        amount_bnb: float,
        amount_usd: float,
        counter: int,
    ) -> str:
        """Format a freshies alert (Freshies / Big Freshies / Low MC)."""
        
        # Build indicator emojis
        indicators = []
        if classification.is_first_mention:
            indicators.append("⭐️")
        if classification.launchpad_emoji:
            indicators.append(classification.launchpad_emoji)
        if classification.is_usdt:
            indicators.append("💲")
        if classification.is_whale:
            indicators.append("🐳")
        elif classification.is_dolphin:
            indicators.append("🐬")
        
        indicator_str = " ".join(indicators) + (" " if indicators else "")
        
        # Amount display
        if classification.is_usdt:
            amount_str = f"${amount_usd:.0f}"
        else:
            amount_str = f"{amount_bnb:.4f}"
        
        # Socials
        socials = []
        if token.telegram:
            socials.append(f"<a href=\"{token.telegram}\">TG</a>")
        if token.website:
            socials.append(f"<a href=\"{token.website}\">WB</a>")
        if token.twitter:
            socials.append(f"<a href=\"{token.twitter}\">TW</a>")
        socials_str = " ".join(socials) if socials else ""
        
        # Trading links
        trading_links = self._format_trading_links(token.address)
        
        # Format alert based on channel
        channel_title = classification.channel_title
        
        message = f"""🟡 BSC {channel_title} [BBB]
[{counter}] {indicator_str}${token.symbol} {token.name} {amount_str} {wallet_classification.funding_source} {wallet_classification.funding_time_ago}
<code>{token.address}</code>
👶 {stats.fresh_buys} 🔶 {stats.fresh_partial_sells} ♦️ {stats.fresh_full_sells}
MC: {token.mc_string} | CA: {token.age_string}{' | ' + socials_str if socials_str else ''}
{trading_links}"""
        
        return message.strip()
    
    def format_dormants_alert(
        self,
        token: BSCTokenData,
        classification: BSCChannelClassification,
        wallet_classification,
        amount_bnb: float,
        amount_usd: float,
        counter: int,
    ) -> str:
        """Format a dormants/semi-dormants alert."""
        
        # Build indicator emojis
        indicators = []
        if classification.is_first_mention:
            indicators.append("⭐️")
        if classification.launchpad_emoji:
            indicators.append(classification.launchpad_emoji)
        if wallet_classification.dormant_emoji:
            indicators.append(wallet_classification.dormant_emoji)
        if classification.is_usdt:
            indicators.append("💲")
        if classification.is_whale:
            indicators.append("🐳")
        elif classification.is_dolphin:
            indicators.append("🐬")
        
        indicator_str = " ".join(indicators) + (" " if indicators else "")
        
        # Amount display
        if classification.is_usdt:
            amount_str = f"${amount_usd:.0f}"
        else:
            amount_str = f"{amount_bnb:.4f}"
        
        # Trading links
        trading_links = self._format_trading_links(token.address)
        
        # Format alert
        channel_title = classification.channel_title
        
        message = f"""🟡 BSC {channel_title} [BBB]
[{counter}] {indicator_str}${token.symbol} {token.name} {amount_str} {token.mc_string}
<code>{token.address}</code>
LS: {wallet_classification.last_activity_days}d | CA: {token.age_string} | [P]
{trading_links}"""
        
        return message.strip()
    
    def _format_trading_links(self, contract_address: str) -> str:
        """Format trading bot quick links for BSC."""
        # Links based on screenshots: SGM | MAE | PRO | BSB | GMGN
        return f"""<a href="https://t.me/sigma_trading_bot?start={contract_address}">SGM</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MAE</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">PRO</a> | <a href="https://bsb.tools/token/bsc/{contract_address}">BSB</a> | <a href="https://gmgn.ai/bsc/token/{contract_address}">GMGN</a>"""


# Singleton
_bot: Optional[BSCTelegramBot] = None


def get_bsc_telegram_bot() -> BSCTelegramBot:
    """Get singleton BSC telegram bot."""
    global _bot
    if _bot is None:
        _bot = BSCTelegramBot()
    return _bot
