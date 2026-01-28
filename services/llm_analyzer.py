"""
Trench Tool V1 - LLM Analyzer
Uses Google Gemini to analyze Twitter profiles and websites for organic vs botted signals.
"""

import logging
import re
from typing import Optional, Dict
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMAnalysis:
    """Result of LLM analysis."""
    twitter_score: int  # 0-100 organic score
    website_score: int  # 0-100 organic score
    twitter_reasoning: str
    website_reasoning: str
    overall_assessment: str


class GeminiAnalyzer:
    """
    Uses Google Gemini to analyze social profiles and websites.
    Scores content for organic vs botted/scam signals.
    """
    
    def __init__(self, api_keys: list[str]):
        self.api_keys = api_keys
        self.current_key_index = 0
        self._initialized_keys = set()
        self._setup_current_key()

    def _setup_current_key(self):
        """Configure Gemini with the current API key."""
        if not self.api_keys:
            self._has_lib = False
            return
            
        api_key = self.api_keys[self.current_key_index]
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash') # Using 2.0 flash as it's more stable/available
            self._has_lib = True
            self._initialized_keys.add(api_key)
            logger.info(f"[LLM] Gemini configured with key index {self.current_key_index}")
        except ImportError:
            logger.error("[LLM] google-generativeai library not installed.")
            self._has_lib = False
        except Exception as e:
            logger.error(f"[LLM] Error configuring Gemini key: {e}")
            self._has_lib = False

    def _rotate_key(self):
        """Rotate to the next API key."""
        if len(self.api_keys) <= 1:
            return False
            
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._setup_current_key()
        return True

    async def _call_gemini(self, prompt: str) -> tuple[int, str]:
        """Call Gemini API using official library."""
        if not self._has_lib:
            return 50, "Library not installed"
            
        logger.info(f"[LLM] Calling Gemini model: {self.model.model_name}")
        
        try:
            # Run in executor since the library is synchronous
            import asyncio
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config={'temperature': 0.3}
            )
            
            text = response.text
            
            # Parse JSON from response
            import json
            import re
            
            # Find JSON in response
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                result = json.loads(json_match.group())
                score = int(result.get("score", 50))
                reasoning = result.get("reasoning", "No reasoning provided")
                return min(100, max(0, score)), reasoning
            
            return 50, "Could not parse response"
            
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"[LLM] Gemini Quota Exceeded (Key {self.current_key_index}). Rotating...")
                
                # Try to rotate
                rotated = self._rotate_key()
                
                # If we rotated back to the start (or only have 1 key), we need to wait
                # simple logic: if rotated is True, we just switched to a new key.
                # But if all keys are exhausted quickly, we still need backoff.
                # For now, let's just add a small delay if we rotated, and a BIG delay if we looped.
                
                import asyncio
                # Retry
                try:
                    # Logic: If we just hit a rate limit, the next key MIGHT be free.
                    # But if we are blasting requests, we might hit limits on all keys.
                    # Let's simple retry with the new key.
                    if rotated:
                        return await self._call_gemini(prompt)
                    else:
                        # Single key or failed to rotate - wait and retry
                        wait_time = 60
                        logger.warning(f"[LLM] All keys exhausted or single key. Sleeping {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        return await self._call_gemini(prompt)
                except Exception as retry_e:
                     logger.error(f"[LLM] Retry failed: {retry_e}")
            
            logger.warning(f"[LLM] Gemini request failed: {e}")
            return 50, "Analysis unavailable"

    async def analyze_twitter_profile(
        self,
        username: str,
        bio: str = "",
        follower_count: int = 0,
        tweet_samples: list = None,
    ) -> tuple[int, str]:
        """
        Analyze a Twitter profile for organic vs botted signals.
        Returns (score 0-100, reasoning).
        """
        tweet_text = "\n".join(tweet_samples[:5]) if tweet_samples else "No tweets available"
        
        prompt = f"""Analyze this crypto token Twitter profile for authenticity.
Rate it 0-100 where 100 is completely organic/legitimate and 0 is definitely botted/scam.

Profile:
- Username: @{username}
- Bio: {bio or 'No bio'}
- Followers: {follower_count}
- Recent tweets: {tweet_text}

Look for red flags:
- Generic/template bio language
- Fake engagement patterns
- Copy-paste promotional content
- Suspicious follower to engagement ratio
- Unrealistic promises
- No genuine community interaction

Green flags:
- Original, specific content
- Genuine community engagement
- Realistic project updates
- Transparent team info
- Technical discussions

Respond with ONLY a JSON object:
{{"score": <0-100>, "reasoning": "<brief 1-2 sentence explanation>"}}"""

        try:
            score, reasoning = await self._call_gemini(prompt)
            return score, reasoning
        except Exception as e:
            logger.warning(f"[LLM] Twitter analysis failed: {e}")
            return 50, "Analysis unavailable"
    
    async def analyze_website(
        self,
        url: str,
        page_content: str = "",
    ) -> tuple[int, str]:
        """
        Analyze a website for legitimacy signals.
        Returns (score 0-100, reasoning).
        """
        # Truncate content to avoid token limits
        content_preview = page_content[:2000] if page_content else "No content available"
        
        prompt = f"""Analyze this crypto token website for authenticity.
Rate it 0-100 where 100 is completely legitimate and 0 is definitely a scam.

Website: {url}
Content preview: {content_preview}

Look for red flags:
- Template/clone site indicators
- Unrealistic promises (1000x, guaranteed returns)
- No team information
- Fake partnerships or audits
- Pressure tactics (buy now! limited time!)
- Poor grammar/spelling
- No whitepaper or roadmap

Green flags:
- Original design and content
- Clear team profiles with verifiable info
- Realistic roadmap
- Legitimate audit links
- Active GitHub/development
- Clear tokenomics

Respond with ONLY a JSON object:
{{"score": <0-100>, "reasoning": "<brief 1-2 sentence explanation>"}}"""

        try:
            score, reasoning = await self._call_gemini(prompt)
            return score, reasoning
        except Exception as e:
            logger.warning(f"[LLM] Website analysis failed: {e}")
            return 50, "Analysis unavailable"
    
    async def full_analysis(
        self,
        twitter_username: str = None,
        twitter_bio: str = "",
        twitter_followers: int = 0,
        tweet_samples: list = None,
        website_url: str = None,
        website_content: str = "",
    ) -> LLMAnalysis:
        """Run full LLM analysis on both Twitter and website."""
        twitter_score = 50
        twitter_reasoning = "No Twitter profile"
        website_score = 50
        website_reasoning = "No website"
        
        if twitter_username:
            twitter_score, twitter_reasoning = await self.analyze_twitter_profile(
                username=twitter_username,
                bio=twitter_bio,
                follower_count=twitter_followers,
                tweet_samples=tweet_samples or [],
            )
            logger.info(f"[LLM] Twitter @{twitter_username}: {twitter_score}/100 - {twitter_reasoning}")
        
        if website_url:
            website_score, website_reasoning = await self.analyze_website(
                url=website_url,
                page_content=website_content,
            )
            logger.info(f"[LLM] Website {website_url}: {website_score}/100 - {website_reasoning}")
        
        overall = f"Twitter: {twitter_score}/100, Website: {website_score}/100"
        
        return LLMAnalysis(
            twitter_score=twitter_score,
            website_score=website_score,
            twitter_reasoning=twitter_reasoning,
            website_reasoning=website_reasoning,
            overall_assessment=overall,
        )


# Singleton
_gemini_analyzer: GeminiAnalyzer | None = None


def get_gemini_analyzer() -> GeminiAnalyzer:
    """Get the singleton Gemini analyzer."""
    global _gemini_analyzer
    if _gemini_analyzer is None:
        from config import settings
        # Support both single GEMINI_API_KEY and comma-separated GEMINI_API_KEYS
        api_keys = []
        
        raw_keys = getattr(settings, 'gemini_api_keys', None) or getattr(settings, 'gemini_api_key', None)
        if raw_keys:
            if isinstance(raw_keys, list):
                api_keys = raw_keys
            else:
                api_keys = [k.strip() for k in str(raw_keys).split(',') if k.strip()]
        
        if not api_keys:
            raise ValueError("GEMINI_API_KEY(S) not configured in .env")
            
        _gemini_analyzer = GeminiAnalyzer(api_keys)
    return _gemini_analyzer
