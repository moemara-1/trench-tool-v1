"""
Trench Tool V1 - Socials Checker
Prioritizes tokens with strong social signals.
Validates and scores social presence (Twitter, Telegram, Website).
"""

import logging
import re
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass

import httpx

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class SocialProfile:
    """Social profile for a token."""
    token_address: str
    twitter_url: Optional[str]
    telegram_url: Optional[str]
    website_url: Optional[str]
    twitter_followers: int
    has_verified_twitter: bool
    has_active_telegram: bool
    social_score: int  # 0-100 (basic score)
    checked_at: datetime
    # Enhanced scoring fields
    smart_followers: int = 0
    enhanced_score: int = 0  # 0-100 (LLM + smart followers score)
    llm_twitter_score: int = 0
    llm_website_score: int = 0
    llm_reasoning: str = ""


class SocialsChecker:
    """
    Checks and scores token social presence.
    
    Strong socials can indicate:
    - More serious project
    - Marketing effort
    - Community building
    """
    
    def __init__(self):
        self._profiles: Dict[str, SocialProfile] = {}
        self._alerted_tokens: set = set()  # Track tokens we've already alerted
        self._alerts_sent = 0
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client
    
    async def check_socials(
        self,
        token_address: str,
        token_data: dict = None,
    ) -> Optional[SocialProfile]:
        """
        Check social links for a token.
        Returns SocialProfile if socials found.
        """
        if token_address in self._profiles:
            logger.debug(f"[Socials] CACHE HIT: token={token_address[:12]}...")
            return self._profiles[token_address]
        
        logger.debug(f"[Socials] CHECKING: token={token_address[:12]}...")
        
        twitter_url = None
        telegram_url = None
        website_url = None
        twitter_followers = 0
        
        # Extract socials from token data (e.g. from Dexscreener)
        if token_data:
            # Handle both old format (nested info.socials) and new format (direct fields)
            socials = token_data.get("info", {}).get("socials", [])
            for social in socials:
                social_type = social.get("type", "").lower()
                url = social.get("url", "")
                if social_type == "twitter":
                    twitter_url = url
                elif social_type == "telegram":
                    telegram_url = url
            
            websites = token_data.get("info", {}).get("websites", [])
            if websites:
                website_url = websites[0].get("url", "")
            
            # Also check direct fields (from EnhancedTokenData)
            if not twitter_url:
                twitter_url = token_data.get("twitter")
            if not telegram_url:
                telegram_url = token_data.get("telegram")
            if not website_url:
                website_url = token_data.get("website")
        
        # Calculate social score
        score = 0
        if twitter_url:
            score += 30
            # Would fetch follower count here
        if telegram_url:
            score += 25
        if website_url:
            score += 20
        
        profile = SocialProfile(
            token_address=token_address,
            twitter_url=twitter_url,
            telegram_url=telegram_url,
            website_url=website_url,
            twitter_followers=twitter_followers,
            has_verified_twitter=False,
            has_active_telegram=telegram_url is not None,
            social_score=score,
            checked_at=datetime.utcnow(),
        )
        
        self._profiles[token_address] = profile
        
        logger.info(f"📱 [Socials] CHECKED: token={token_address[:12]}... | score={score}/100 | twitter={'✓' if twitter_url else '✗'} | telegram={'✓' if telegram_url else '✗'} | website={'✓' if website_url else '✗'}")
        return profile
    
    def is_strong_socials(self, profile: SocialProfile) -> bool:
        """Check if socials are strong enough for an alert (and not already alerted)."""
        # Check if already alerted for this token
        if profile.token_address in self._alerted_tokens:
            logger.debug(f"[Socials] SKIPPED (already alerted): token={profile.token_address[:12]}...")
            return False
        
        is_strong = profile.social_score >= 50  # Has at least Twitter + Telegram
        if is_strong:
            logger.info(f"📱 [Socials] STRONG SOCIALS: token={profile.token_address[:12]}... | score={profile.social_score}/100")
        return is_strong
    
    def mark_alerted(self, token_address: str):
        """Mark a token as having been alerted (to prevent duplicates)."""
        self._alerted_tokens.add(token_address)
    
    async def analyze_enhanced(self, profile: SocialProfile) -> SocialProfile:
        """
        Run enhanced analysis using smart followers ONLY (LLM Disabled).
        Only call this after basic score >= 50.
        
        Scoring weights (Rebalanced):
        - Smart followers: 85 points (85%)
        - Presence bonus: 15 points (15%)
        - LLM Twitter: 0 points (Disabled)
        - LLM Website: 0 points (Disabled)
        """
        try:
            from services.smart_follower_scraper import get_smart_follower_scraper
            # from services.llm_analyzer import get_gemini_analyzer # Disabled to avoid 429s
            
            smart_score = 0
            twitter_score = 0  
            website_score = 0
            
            # 1. Get smart follower data (85% weight)
            if profile.twitter_url:
                scraper = get_smart_follower_scraper()
                smart_data = await scraper.scrape_profile(profile.twitter_url)
                
                if smart_data:
                    profile.smart_followers = smart_data.smart_followers
                    profile.twitter_followers = smart_data.total_followers
                    
                    # Score based on smart follower count (Scaled to 85 max)
                    # 0-10 smart followers = 0-15 pts
                    # 10-50 = 15-45 pts
                    # 50-100 = 45-65 pts
                    # 100+ = 65-85 pts
                    sf = smart_data.smart_followers
                    if sf >= 100:
                        # Max out at 85 for super high counts
                        smart_score = min(85, 65 + (sf - 100) // 5)
                    elif sf >= 50:
                        smart_score = 45 + (sf - 50) * 0.4  # 20 pts range (45-65) for 50 followers -> 0.4 pts per follower
                    elif sf >= 10:
                        smart_score = 15 + (sf - 10) * 0.75 # 30 pts range (15-45) for 40 followers -> 0.75 pts per follower
                    else:
                        smart_score = sf * 1.5              # 15 pts range (0-15) for 10 followers -> 1.5 pts per follower
                    
                    smart_score = int(smart_score)
                    logger.info(f"[Socials] Smart followers: {sf} -> {smart_score}/85 pts")
            
            # 2. LLM analysis (Disabled)
            profile.llm_twitter_score = 0
            profile.llm_website_score = 0
            profile.llm_reasoning = "LLM Analysis Disabled"
            
            # 3. Calculate enhanced score
            # Smart followers: 85% (0-85 pts)
            # Presence bonus: 15% (0-15 pts)
            
            # Presence bonus: having all socials gives bonus
            presence_pts = 0
            if profile.twitter_url:
                presence_pts += 5
            if profile.telegram_url:
                presence_pts += 5
            if profile.website_url:
                presence_pts += 5
            
            enhanced = smart_score + presence_pts
            profile.enhanced_score = min(100, enhanced)
            
            logger.info(f"📱 [Socials] ENHANCED SCORE: {profile.enhanced_score}/100 (smart={smart_score}, pres={presence_pts}, llm=disabled)")
            
        except Exception as e:
            logger.error(f"[Socials] Enhanced analysis error: {e}")
            profile.enhanced_score = profile.social_score  # Fallback to basic
        
        return profile
    
    def is_enhanced_socials(self, profile: SocialProfile) -> bool:
        """Check if enhanced score exceeds threshold (>70)."""
        if profile.token_address in self._alerted_tokens:
            return False
        return profile.enhanced_score > 70

    def is_alertable_socials(self, profile: SocialProfile) -> bool:
        """Check if a social profile is strong enough to alert."""
        if profile.token_address in self._alerted_tokens:
            return False
        return profile.enhanced_score > 70 or profile.social_score >= 75

    def get_alertable_profiles(self, limit: int = 2) -> list[SocialProfile]:
        """Return unalerted profiles ready for the Socials topic."""
        if limit <= 0:
            return []
        profiles = [
            profile
            for profile in self._profiles.values()
            if self.is_alertable_socials(profile)
        ]
        profiles.sort(
            key=lambda profile: (
                max(profile.enhanced_score, profile.social_score),
                profile.checked_at,
            ),
            reverse=True,
        )
        return profiles[:limit]
    
    def _extract_username(self, url: str) -> Optional[str]:
        """Extract Twitter username from URL."""
        if not url:
            return None
        match = re.search(r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)', url)
        return match.group(1) if match else None
    
    async def format_socials_alert(
        self,
        ticker: str,
        token_name: str,
        contract_address: str,
        profile: SocialProfile,
        market_cap_str: str = "?",
        coin_age_str: str = "?",
    ) -> str:
        """
        Format a socials check alert.
        
        📱 SOL Strong Socials
        $TICKER TokenName | Score: 75/100
        🐦 Twitter | 📱 Telegram | 🌐 Website
        MC: $500K | CA: 2d
        contract_address
        PH | AX | TJ | BA | PR | BL | MA | MT | NE | XX | PF
        """
        from services.api_clients import get_token_fetcher
        
        # Build social indicators with hyperlinks
        socials = []
        if profile.twitter_url:
            socials.append(f'<a href="{profile.twitter_url}">🐦 Twitter</a>')
        if profile.telegram_url:
            socials.append(f'<a href="{profile.telegram_url}">📱 Telegram</a>')
        if profile.website_url:
            socials.append(f'<a href="{profile.website_url}">🌐 Website</a>')
        
        socials_str = " | ".join(socials) if socials else "None"
        
        # Get pair address for Axiom link
        pair_address = await get_token_fetcher().get_pair_address(contract_address)
        if not pair_address:
            pair_address = contract_address
        
        # Build enhanced score line
        score_line = f"Score: {profile.enhanced_score}/100"
        if profile.smart_followers > 0:
            score_line += f" | 🧠 {profile.smart_followers} smart followers"
        
        # Add LLM reasoning if available
        llm_line = ""
        if profile.llm_reasoning:
            llm_line = f"\n💡 {profile.llm_reasoning}"
        
        message = f"""📱 SOL Enhanced Socials
${ticker} {token_name} | {score_line}
{socials_str}{llm_line}
MC: {market_cap_str} | CA: {coin_age_str}
<code>{contract_address}</code>
<a href="https://photon-sol.tinyastro.io/en/lp/{contract_address}">PH</a> | <a href="https://axiom.trade/meme/{pair_address}?chain=sol">AX</a> | <a href="https://t.me/paris_trojanbot?start={contract_address}">TJ</a> | <a href="https://t.me/BananaGunSolana_bot?start={contract_address}">BA</a> | <a href="https://trade.padre.gg/trade/solana/{contract_address}">PR</a> | <a href="https://t.me/BloomSolana_bot?start={contract_address}">BL</a> | <a href="https://t.me/MaestroSniperBot?start={contract_address}">MA</a> | <a href="https://t.me/MaestroProBot?start={contract_address}">MT</a> | <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={contract_address}">NE</a> | <a href="https://dexscreener.com/solana/{contract_address}">XX</a> | <a href="https://pump.fun/{contract_address}">PF</a>"""
        
        return message.strip()
    
    def increment_alerts(self):
        """Increment alert counter."""
        self._alerts_sent += 1
    
    def get_stats(self) -> dict:
        """Get checker statistics without mutating/logging profile state."""
        basic_count = sum(
            1
            for profile in self._profiles.values()
            if profile.token_address not in self._alerted_tokens and profile.social_score >= 50
        )
        alertable_count = sum(1 for profile in self._profiles.values() if self.is_alertable_socials(profile))
        rejected_by_reason: dict[str, int] = {}
        for profile in self._profiles.values():
            reason = self._social_rejection_reason(profile)
            if reason:
                rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
        return {
            "tokens_checked": len(self._profiles),
            "basic_socials": basic_count,
            "alertable_socials": alertable_count,
            "strong_socials": alertable_count,
            "rejected_socials": sum(rejected_by_reason.values()),
            "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
            "alerts_sent": self._alerts_sent,
        }

    def _social_rejection_reason(self, profile: SocialProfile) -> Optional[str]:
        if profile.token_address in self._alerted_tokens:
            return "already_alerted"
        if self.is_alertable_socials(profile):
            return None
        if not (profile.twitter_url or profile.telegram_url or profile.website_url):
            return "no_socials"
        return "partial_socials_below_threshold"


# Singleton
_socials_checker: SocialsChecker | None = None


def get_socials_checker() -> SocialsChecker:
    """Get the singleton socials checker."""
    global _socials_checker
    if _socials_checker is None:
        _socials_checker = SocialsChecker()
    return _socials_checker
