"""
Trench Tool V1 - Smart Follower Scraper
Uses browser automation with Playwright to extract smart follower data
from Twitter profiles using the FrontrunPro extension.
"""

import logging
import asyncio
import re
import os
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SmartFollowerData:
    """Smart follower data from FrontrunPro."""
    twitter_username: str
    total_followers: int
    smart_followers: int  # Profitable crypto traders following
    smart_follower_ratio: float  # smart_followers / total_followers
    account_age_days: int
    tweet_count: int
    bio: str
    recent_tweets: list
    scraped_at: datetime


class SmartFollowerScraper:
    """
    Scrapes Twitter profiles for smart follower data using FrontrunPro extension.
    
    FrontrunPro injects "smart follower" indicators on Twitter profiles.
    This scraper:
    1. Loads Chrome with FrontrunPro extension
    2. Navigates to Twitter profile
    3. Waits for FrontrunPro to inject smart follower data
    4. Extracts the smart follower count from injected DOM elements
    """
    
    # Path to FrontrunPro extension (user must download and place here)
    EXTENSION_PATH = Path(__file__).parent.parent / "extensions" / "frontrunpro"
    
    def __init__(self):
        self._cache: Dict[str, SmartFollowerData] = {}
        self._browser = None
        self._context = None
        self._playwright = None
        self._initialized = False
        self._extension_loaded = False
    
    async def initialize(self):
        """Initialize Playwright browser with FrontrunPro extension."""
        if self._initialized:
            return
        
        try:
            from playwright.async_api import async_playwright
            
            self._playwright = await async_playwright().start()
            
            # Find extension path (look for latest version folder)
            extension_base = self.EXTENSION_PATH
            extension_path = None
            
            if os.path.exists(extension_base) and os.path.isdir(extension_base):
                # Find version folders (e.g., 0.0.179_0)
                version_folders = [
                    f for f in os.listdir(extension_base) 
                    if os.path.isdir(os.path.join(extension_base, f)) and 
                    f[0].isdigit()  # Version folders start with digit
                ]
                
                if version_folders:
                    # Sort to get latest version
                    version_folders.sort(reverse=True)
                    extension_path = str(os.path.join(extension_base, version_folders[0]))
                    logger.info(f"[SmartFollower] Found FrontrunPro version: {version_folders[0]}")
            
            if extension_path and os.path.exists(os.path.join(extension_path, "manifest.json")):
                # Launch with extension
                self._browser = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(Path(__file__).parent.parent / ".browser_data"),
                    headless=False,  # Extensions require headed mode
                    args=[
                        f'--disable-extensions-except={extension_path}',
                        f'--load-extension={extension_path}',
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--start-minimized',
                        '--window-position=-10000,-10000',
                    ],
                    viewport={'width': 1280, 'height': 720},
                )
                self._extension_loaded = True
                logger.info(f"[SmartFollower] Browser initialized WITH FrontrunPro extension from {extension_path}")
            else:
                # Launch without extension - use estimation
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                    ]
                )
                self._context = await self._browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                logger.warning(f"[SmartFollower] FrontrunPro extension not found or invalid")
                logger.warning("[SmartFollower] To enable: Copy extension from Chrome to backend/extensions/frontrunpro/")
            
            self._initialized = True
            
        except ImportError:
            logger.warning("[SmartFollower] Playwright not installed. Run: pip install playwright && playwright install chromium")
            self._initialized = False
        except Exception as e:
            logger.error(f"[SmartFollower] Failed to initialize browser: {e}")
            self._initialized = False
    
    async def cleanup(self):
        """Cleanup browser resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False
    
    async def scrape_profile(self, twitter_url: str) -> Optional[SmartFollowerData]:
        """
        Scrape a Twitter profile for smart follower data.
        
        With FrontrunPro extension: Extracts real smart follower count
        Without extension: Returns estimated data based on heuristics
        """
        # Check cache
        username = self._extract_username(twitter_url)
        if not username:
            return None
        
        # DEBUG: Skip cache to force fresh scan
        # if username in self._cache:
        #     cached = self._cache[username]
        #     # Cache for 1 hour
        #     if (datetime.utcnow() - cached.scraped_at).total_seconds() < 3600:
        #         logger.debug(f"[SmartFollower] Cache hit for @{username}")
        #         return cached
        
        logger.info(f"[SmartFollower] Starting FRESH scrape for @{username}...")
        
        if not self._initialized:
            await self.initialize()
        
        if not self._initialized:
            # Fallback: Return estimated data without browser
            return await self._fallback_scrape(username)
        
        try:
            # Get page context
            if self._extension_loaded:
                page = await self._browser.new_page()
            else:
                page = await self._context.new_page()
            
            # Navigate to Twitter profile
            await page.bring_to_front()
            profile_url = f"https://x.com/{username}"
            await page.goto(profile_url, wait_until='domcontentloaded', timeout=60000)
            
            # Wait for page and FrontrunPro to load (needs time to inject)
            await asyncio.sleep(10)
            
            # Always try FrontrunPro extraction first
            data = await self._extract_frontrunpro_data(page, username)
            
            await page.close()
            
            if data:
                self._cache[username] = data
                logger.info(f"[SmartFollower] @{username}: {data.smart_followers} smart followers / {data.total_followers} total")
            
            return data
            
        except Exception as e:
            logger.warning(f"[SmartFollower] Error scraping @{username}: {e}")
            return await self._fallback_scrape(username)
    
    async def _extract_frontrunpro_data(self, page, username: str) -> Optional[SmartFollowerData]:
        """Extract smart follower data from FrontrunPro-injected DOM elements."""
        try:
            # Wait for FrontrunPro to inject its elements
            await asyncio.sleep(3)
            
            smart_followers = 0
            
            # Robust extraction based on debugged structure:
            # <h6 ...><span ...>2394</span> Smart Followers</h6>
            
            # DEBUG: Check if we are stuck on login page
            try:
                if await page.query_selector('a[href="/login"]'):
                    logger.warning(f"[SmartFollower] Detected login prompt for @{username}. Extraction may fail.")
            except:
                pass
                
            # Method 1: Get by text "Smart Followers" and check parent text
            try:
                # Try finding any element with the text (case-insensitive)
                smart_elem = await page.get_by_text("Smart Followers", exact=False).first
                
                # If get_by_text fails, try query_selector with xpath
                if not await smart_elem.count():
                    smart_elem = await page.query_selector('xpath=//*[contains(text(), "Smart Followers")]')
                
                if smart_elem:
                    # Check the element itself
                    text = await (smart_elem.inner_text() if hasattr(smart_elem, 'inner_text') else smart_elem.evaluate('el => el.innerText'))
                    logger.debug(f"[SmartFollower] Found element text: '{text}'")
                    match = re.search(r'(\d+[\d,.]*)\s*Smart', text, re.IGNORECASE)
                    
                    # If not found in element, check parent
                    if not match:
                        parent = await (page.evaluate_handle('el => el.parentElement', smart_elem) if hasattr(smart_elem, 'count') else smart_elem.evaluate_handle('el => el.parentElement'))
                        if parent:
                            text = await parent.evaluate('el => el.innerText')
                            logger.debug(f"[SmartFollower] Parent text: '{text}'")
                            match = re.search(r'(\d+[\d,.]*)\s*Smart', text, re.IGNORECASE)
                    
                    if match:
                        num_str = match.group(1).replace(',', '').replace('.', '') # Handle both 2,395 and 2.395 if applicable
                        smart_followers = int(float(num_str))
                        logger.info(f"[SmartFollower] Found via text match: {smart_followers}")
                else:
                    logger.debug(f"[SmartFollower] No element with 'Smart Followers' found via get_by_text/xpath")
            except Exception as e:
                logger.debug(f"[SmartFollower] Method 1 extraction failed: {e}")
            
            # Method 2: Fallback to H6 selection
            if smart_followers == 0:
                try:
                    h6_elems = await page.query_selector_all('h6')
                    logger.debug(f"[SmartFollower] Found {len(h6_elems)} h6 elements")
                    for h6 in h6_elems:
                        text = await h6.inner_text()
                        if "Smart Followers" in text:
                            text = text.replace('\n', ' ')
                            match = re.search(r'(\d+[\d,.]*)\s*Smart', text, re.IGNORECASE)
                            if match:
                                num_str = match.group(1).replace(',', '').replace('.', '')
                                smart_followers = int(float(num_str))
                                logger.info(f"[SmartFollower] Found via H6: {smart_followers}")
                                break
                except Exception as e:
                    logger.debug(f"[SmartFollower] Method 2 extraction failed: {e}")
            
            total_followers = 0
            
            # Get total followers
            followers_elem = await page.query_selector('a[href$="/verified_followers"] span span, a[href$="/followers"] span span')
            if followers_elem:
                text = await followers_elem.inner_text()
                total_followers = self._parse_follower_count(text)
            
            # Get bio
            bio = ""
            bio_elem = await page.query_selector('[data-testid="UserDescription"]')
            if bio_elem:
                bio = await bio_elem.inner_text()
            
            # Get tweets
            tweets = []
            tweet_elems = await page.query_selector_all('[data-testid="tweetText"]')
            for elem in tweet_elems[:5]:
                try:
                    tweet_text = await elem.inner_text()
                    tweets.append(tweet_text)
                except:
                    pass
            
            # If still no smart followers found, estimate
            if smart_followers == 0:
                logger.warning(f"[SmartFollower] Scraper failed to find smart count for @{username}, falling back to estimation")
                smart_followers = self._estimate_smart_followers(total_followers, tweets)
            
            return SmartFollowerData(
                twitter_username=username,
                total_followers=total_followers,
                smart_followers=smart_followers,
                smart_follower_ratio=smart_followers / max(total_followers, 1),
                account_age_days=0,
                tweet_count=0,
                bio=bio,
                recent_tweets=tweets,
                scraped_at=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.warning(f"[SmartFollower] FrontrunPro extraction error: {e}")
            return await self._extract_profile_data(page, username)
    
    async def _extract_profile_data(self, page, username: str) -> Optional[SmartFollowerData]:
        """Extract profile data from loaded Twitter page."""
        try:
            # Get follower count - use verified_followers selector that works
            total_followers = 0
            follower_selectors = [
                'a[href$="/verified_followers"] span',
                'a[href$="/followers"] span',
            ]
            
            for selector in follower_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for elem in elements:
                        text = await elem.inner_text()
                        if text and not text.lower() in ['followers', 'following']:
                            count = self._parse_follower_count(text)
                            if count > 0:
                                total_followers = count
                                logger.debug(f"[SmartFollower] Found followers: {total_followers}")
                                break
                except:
                    continue
                if total_followers > 0:
                    break
            
            # Get bio from user description
            bio = ""
            bio_selectors = [
                '[data-testid="UserDescription"]',
                '[data-testid="primaryColumn"] [dir="auto"]',
            ]
            for selector in bio_selectors:
                try:
                    bio_elem = await page.query_selector(selector)
                    if bio_elem:
                        bio = await bio_elem.inner_text()
                        if bio and len(bio) > 20:  # Reasonable bio length
                            break
                except:
                    continue
            
            # Get recent tweets
            tweets = []
            tweet_elems = await page.query_selector_all('[data-testid="tweetText"]')
            for elem in tweet_elems[:5]:
                try:
                    tweet_text = await elem.inner_text()
                    if tweet_text:
                        tweets.append(tweet_text)
                except:
                    pass
            
            # Estimate smart followers based on crypto signals
            smart_followers = self._estimate_smart_followers(total_followers, tweets)
            
            logger.info(f"[SmartFollower] Extracted @{username}: {total_followers:,} followers, {smart_followers} smart (estimated)")
            
            return SmartFollowerData(
                twitter_username=username,
                total_followers=total_followers,
                smart_followers=smart_followers,
                smart_follower_ratio=smart_followers / max(total_followers, 1),
                account_age_days=0,
                tweet_count=0,
                bio=bio,
                recent_tweets=tweets,
                scraped_at=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.warning(f"[SmartFollower] Error extracting data: {e}")
            return None
    
    async def _fallback_scrape(self, username: str) -> SmartFollowerData:
        """Fallback when browser is not available - return minimal data."""
        return SmartFollowerData(
            twitter_username=username,
            total_followers=0,
            smart_followers=0,
            smart_follower_ratio=0.0,
            account_age_days=0,
            tweet_count=0,
            bio="",
            recent_tweets=[],
            scraped_at=datetime.utcnow(),
        )
    
    def _extract_username(self, url: str) -> Optional[str]:
        """Extract username from Twitter URL."""
        if not url:
            return None
        
        # Handle various Twitter/X URL formats
        patterns = [
            r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)',
            r'@([a-zA-Z0-9_]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                # Filter out common non-profile paths
                if username.lower() not in ['home', 'explore', 'search', 'settings', 'messages', 'i']:
                    return username
        
        return None
    
    def _parse_follower_count(self, text: str) -> int:
        """Parse follower count from Twitter display format (e.g., '10.5K')."""
        text = text.strip().upper()
        
        # Remove commas
        text = text.replace(',', '')
        
        multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}
        
        for suffix, mult in multipliers.items():
            if suffix in text:
                try:
                    num = float(text.replace(suffix, '').strip())
                    return int(num * mult)
                except:
                    pass
        
        try:
            return int(float(text))
        except:
            return 0
    
    def _estimate_smart_followers(self, total_followers: int, tweets: list) -> int:
        """
        Estimate smart followers based on signals.
        
        Heuristics:
        - Crypto-related keywords in tweets boost estimate
        - Very high follower counts may have lower smart ratio
        - Engagement patterns would affect this (not available without API)
        """
        if total_followers == 0:
            return 0
        
        # Check tweets for crypto signals
        crypto_keywords = [
            'sol', 'solana', 'pump', 'token', 'dex', 'hodl', 'moon', 
            'ape', 'degen', 'memecoin', 'crypto', 'blockchain', 'nft',
            'raydium', 'jupiter', 'bonk', 'wen', 'gm', 'wagmi', 'ngmi',
            'alpha', 'whale', 'airdrop', 'mint', 'presale', 'launch'
        ]
        
        crypto_score = 0
        for tweet in tweets:
            tweet_lower = tweet.lower()
            for keyword in crypto_keywords:
                if keyword in tweet_lower:
                    crypto_score += 1
        
        # Base ratio: assume 1-8% of crypto twitter followers are "smart"
        if crypto_score > 10:
            base_ratio = 0.08  # Very crypto-heavy account
        elif crypto_score > 5:
            base_ratio = 0.05  # Moderate crypto content
        elif crypto_score > 0:
            base_ratio = 0.03  # Some crypto content
        else:
            base_ratio = 0.01  # Non-crypto account
        
        # Diminishing returns for very large accounts
        if total_followers > 100000:
            base_ratio *= 0.4
        elif total_followers > 50000:
            base_ratio *= 0.6
        elif total_followers > 10000:
            base_ratio *= 0.8
        
        return int(total_followers * base_ratio)


# Singleton
_scraper: SmartFollowerScraper | None = None


def get_smart_follower_scraper() -> SmartFollowerScraper:
    """Get the singleton smart follower scraper."""
    global _scraper
    if _scraper is None:
        _scraper = SmartFollowerScraper()
    return _scraper
