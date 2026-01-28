"""
Trench Tool V1 - Telegram Bot
Sends formatted alerts to Telegram in BBB style.
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import settings
from models import AlertPriority

logger = logging.getLogger(__name__)


# Priority to emoji mapping
PRIORITY_EMOJI = {
    AlertPriority.CRITICAL: "🔴",
    AlertPriority.HIGH: "🟠",
    AlertPriority.MEDIUM: "🟡",
    AlertPriority.LOW: "🟢",
}

# Launchpad emojis
LAUNCHPAD_EMOJI = {
    "pump.fun": "💊",
    "pumpfun": "💊",
    "meteora": "☄️",
    "raydium": "®️",
    "raydium_clmm": "®️💧",
    "orca": "🐋",
    "bonk": "🐕",
    "moonshot": "🌙",
    "moonit": "🌙",
    "raydium_launchpad": "🔮",
    "sugar": "🍭",
}

# Router emojis
ROUTER_EMOJI = {
    "axiom": "🔳",
    "blur": "🧶",
    "padre": "🏮",
    "telemetry": "🐶",
    "nova": "♋️",
    "bananagun": "🍌",
    "maestro": "Ⓜ️",
    "trojan": "🔱",
    "bloom": "🌸",
    "mintech": "📱",
    "bonk": "🐕",
}


class TelegramAlertBot:
    """Telegram bot for sending trading alerts in BBB style."""
    
    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self._bot: Bot | None = None
    
    @property
    def bot(self) -> Bot:
        if self._bot is None:
            if not self.token:
                raise ValueError("Telegram bot token not configured")
            self._bot = Bot(token=self.token)
        return self._bot
    
    async def format_freshie_alert_bbb(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        amount_sol: float,
        market_cap_str: str,
        coin_age_str: str,
        funding_source: str,
        funding_time: str,
        fresh_buy_count: int = 0,
        fresh_sell_count: int = 0,
        partial_sell_count: int = 0,
        dormant_buy_count: int = 0,
        launchpad: str = None,
        router: str = None,
        is_first_mention: bool = False,
        is_whale: bool = False,
        is_dolphin: bool = False,
        twitter_link: str = None,
    ) -> str:
        """
        Format a freshie alert in compact BBB style:
        
        SOL Freshies [BBB]
        $TICKER TokenName 0.88 💊 MEXC 13d
        👶🏻 29 ♦️ 0 🔶 0 ⏳ 0
        MC: 42.4k | CA: 17m | [X]
        DLLBw7Ecw8pQ8TBxRkY45P6wX9U6PsxpRgzKR7EDpump
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        # Build emoji string for line 2
        emojis = []
        if is_first_mention:
            emojis.append("⭐️")
        if is_whale:
            emojis.append("🐳")
        elif is_dolphin:
            emojis.append("🐬")
        
        # Launchpad emoji
        launchpad_emoji = ""
        if launchpad:
            launchpad_lower = launchpad.lower().replace(".", "").replace(" ", "")
            launchpad_emoji = LAUNCHPAD_EMOJI.get(launchpad_lower, "")
        
        # Router emoji
        router_emoji = ""
        if router:
            router_lower = router.lower().replace(" ", "")
            router_emoji = ROUTER_EMOJI.get(router_lower, "")
        
        emoji_str = " ".join(emojis) + (" " if emojis else "")
        
        # X/Twitter link
        x_link = f'<a href="{twitter_link}">[X]</a>' if twitter_link else ""
        
        # Build message in BBB format
        # Get pair address for Axiom link
        from services.api_clients import get_token_fetcher
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address

        message = f"""🟠 SOL Freshies [BBB]
${ticker} {token_name} {amount_sol:.2f} {launchpad_emoji} {funding_source}  {funding_time}
{emoji_str}👶🏻 {fresh_buy_count} ♦️ {fresh_sell_count} 🔶 {partial_sell_count} ⏳ {dormant_buy_count}
MC: {market_cap_str} | CA: {coin_age_str} {x_link}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://dexscreener.com/solana/{contract_address}">XX</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    async def format_freshie_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        wallet_address: str,
        amount_sol: float,
        market_cap: Optional[float],
        coin_age_minutes: int,
        indicators: dict,
        fresh_buy_count: int = 1,
        fresh_sell_count: int = 0,
        partial_sell_count: int = 0,
        dormant_buy_count: int = 0,
        funding_source: str = "Unknown",
        funding_time: str = "Unknown",
        priority: AlertPriority = AlertPriority.MEDIUM,
        launchpad: str = None,
        router: str = None,
    ) -> str:
        """Format using the new BBB style."""
        # Format market cap
        if market_cap:
            if market_cap >= 1_000_000:
                mc_str = f"{market_cap / 1_000_000:.1f}M"
            elif market_cap >= 1_000:
                mc_str = f"{market_cap / 1_000:.1f}k"
            else:
                mc_str = f"{market_cap:.0f}"
        else:
            mc_str = "?"
        
        # Format coin age
        if coin_age_minutes < 60:
            age_str = f"{coin_age_minutes}m"
        elif coin_age_minutes < 1440:
            hours = coin_age_minutes // 60
            mins = coin_age_minutes % 60
            age_str = f"{hours}h{mins}m" if mins else f"{hours}h"
        else:
            days = coin_age_minutes // 1440
            age_str = f"{days}d"
        
        # Check indicators
        is_first_mention = indicators.get("is_first_mention", False)
        is_whale = amount_sol >= settings.whale_threshold_sol
        is_dolphin = amount_sol >= settings.dolphin_threshold_sol and not is_whale
        
        return await self.format_freshie_alert_bbb(
            ticker=ticker,
            token_name=token_name,
            contract_address=contract_address,
            amount_sol=amount_sol,
            market_cap_str=mc_str,
            coin_age_str=age_str,
            funding_source=funding_source,
            funding_time=funding_time,
            fresh_buy_count=fresh_buy_count,
            fresh_sell_count=fresh_sell_count,
            partial_sell_count=partial_sell_count,
            dormant_buy_count=dormant_buy_count,
            launchpad=launchpad,
            router=router,
            is_first_mention=is_first_mention,
            is_whale=is_whale,
            is_dolphin=is_dolphin,
        )
    
    async def send_alert(
        self,
        message: str,
        chat_id: str = None,
        topic_id: int = None,
        disable_notification: bool = False,
    ) -> Optional[int]:
        """Send an alert message to Telegram.
        
        Args:
            message: The message text
            chat_id: Target chat ID (uses default if None)
            topic_id: Forum topic ID for sending to specific topic (optional)
            disable_notification: Whether to send silently
        """
        target_chat = chat_id or self.chat_id
        
        if not target_chat:
            logger.warning("No chat_id configured, skipping Telegram alert")
            return None
        
        try:
            # Build kwargs for send_message
            kwargs = {
                "chat_id": target_chat,
                "text": message,
                "parse_mode": ParseMode.HTML,
                "disable_web_page_preview": True,
                "disable_notification": disable_notification,
            }
            
            # Add topic ID if specified (for Forum groups)
            if topic_id and topic_id > 0:
                kwargs["message_thread_id"] = topic_id
            
            result = await self.bot.send_message(**kwargs)
            logger.info(f"Sent Telegram alert, message_id: {result.message_id}")
            return result.message_id
            
        except TelegramError as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return None
    
    async def send_freshie_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        wallet_address: str,
        amount_sol: float,
        market_cap: Optional[float],
        coin_age_minutes: int,
        indicators: dict,
        priority: AlertPriority = AlertPriority.MEDIUM,
        **kwargs,
    ) -> Optional[int]:
        """Send a formatted freshie alert."""
        message = await self.format_freshie_alert(
            ticker=ticker,
            token_name=token_name,
            contract_address=contract_address,
            wallet_address=wallet_address,
            amount_sol=amount_sol,
            market_cap=market_cap,
            coin_age_minutes=coin_age_minutes,
            indicators=indicators,
            priority=priority,
            **kwargs,
        )
        
        disable_notification = priority == AlertPriority.LOW
        return await self.send_alert(message, disable_notification=disable_notification)
    
    async def format_dormant_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        amount_sol: float,
        market_cap_str: str,
        coin_age_str: str,
        last_seen_days: int,
        dormant_emoji: str,
        dormant_type: str = "dormants",  # dormants, big_dormants, semi_dormants
        dormant_count: int = 1,
        launchpad_emoji: str = "",
        router_emoji: str = "",
        is_first_mention: bool = False,
        is_whale: bool = False,
        is_dolphin: bool = False,
    ) -> str:
        """
        Format a dormant wallet alert in BBB style.
        
        Headers:
        - ⏳ SOL Dormants
        - ⏳ SOL Big Dormants
        - ⏳ SOL Semi-Dormants
        """
        # Determine header based on dormant type
        headers = {
            "dormants": "SOL Dormants",
            "big_dormants": "SOL Big Dormants",
            "semi_dormants": "SOL Semi-Dormants",
        }
        header = headers.get(dormant_type, "SOL Dormants")
        
        # Build emoji indicators for line 2
        emojis = []
        if is_first_mention:
            emojis.append("⭐️")
        if is_whale:
            emojis.append("🐳")
        elif is_dolphin:
            emojis.append("🐬")
        if router_emoji:
            emojis.append(router_emoji)
        
        emoji_str = " ".join(emojis) + (" " if emojis else "")
        
        # Build message in BBB Dormants format
        # Get pair address for Axiom link
        from services.api_clients import get_token_fetcher
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address

        message = f"""⏳ {header}
{emoji_str}{dormant_emoji} ${ticker} {token_name} {amount_sol:.2f} {launchpad_emoji} ${market_cap_str}
<code>{contract_address}</code>
LS: {last_seen_days}d | CA: {coin_age_str}
<a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a>"""
        
        return message.strip()


# Singleton instance
_telegram_bot: TelegramAlertBot | None = None


def get_telegram_bot() -> TelegramAlertBot:
    """Get the singleton Telegram bot instance."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramAlertBot()
    return _telegram_bot
