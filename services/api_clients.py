"""
Trench Tool V1 - External API Clients
Free APIs for token data, prices, and wallet analysis.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

import httpx

from config import settings
from services.rpc_manager import get_rpc_manager

logger = logging.getLogger(__name__)


# ==================== JUPITER PRICE API ====================

@dataclass
class TokenPrice:
    """Token price from Jupiter."""
    address: str
    price_usd: float
    timestamp: datetime


class JupiterClient:
    """Jupiter API client for prices."""
    
    PRICE_URL = "https://price.jup.ag/v6/price"
    
    def __init__(self):
        self._cache: Dict[str, TokenPrice] = {}
        self._sol_price: float = 200.0  # Default fallback
    
    async def get_price(self, token_address: str) -> Optional[float]:
        """Get token price in USD."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.PRICE_URL,
                    params={"ids": token_address}
                )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                token_data = data.get("data", {}).get(token_address, {})
                
                price = token_data.get("price")
                if price:
                    self._cache[token_address] = TokenPrice(
                        address=token_address,
                        price_usd=float(price),
                        timestamp=datetime.utcnow(),
                    )
                    return float(price)
                
                return None
                
        except Exception as e:
            logger.error(f"Jupiter price error: {e}")
            return None
    
    async def get_sol_price(self) -> float:
        """Get current SOL price in USD."""
        try:
            # SOL mint address
            sol_mint = "So11111111111111111111111111111111111111112"
            price = await self.get_price(sol_mint)
            if price:
                self._sol_price = price
            return self._sol_price
        except:
            return self._sol_price


# ==================== HELIUS ENHANCED API ====================

# Known CEX wallet addresses for funding source detection
CEX_WALLETS = {
    # Binance
    "5tzFs2EyNfJRFYk5xDnRaBZzZj5xM9FqFX1e7VVoS3jq": "Binance",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Binance",
    "2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S": "Binance",
    "5VCwKtCXgCJ6kit5FybXjvriW3xELsFDhYrPSqtJNmcD": "Binance",
    
    # Coinbase
    "GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE": "Coinbase",
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS": "Coinbase",
    
    # Kraken
    "FWznbcNXWQuHTawe9RxvQ2LdCENPAC7KZXLqwKKCzNCX": "Kraken",
    
    # OKX
    "5VCwKtCXgCJ6kit5FybXjvriW3xELsFDhYrPSqtJNmcD": "OKX",
    "ELfBULdfhwLmViTXhS8CnVRDdJvN5KbzToYpr2ivXNk8": "OKX",
    
    # Bybit
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2": "Bybit",
    
    # KuCoin
    "BmFdpraQhkiDQE6SnfG5omcA1VwzqfXrwtNYBwWTymy6": "KuCoin",
    
    # Gate.io
    "u6PJ8DtQuPFnfmwHbGFULQ4u4EgjDiyYKjVEsynXq2w": "Gate.io",
    
    # MEXC
    "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ": "MEXC",
    
    # HTX (Huobi)
    "E3yHoRo8hs6k6ynXPogio3ZEvLXbD7oNb4qgAFW7TXWH": "HTX",
    
    # User provided known addresses
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Binance",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfBKCoP3gKsGbU": "Coinbase",
    "H8sMJSCQxfKiFVcfB3J8q8G6h1r9t4g8r4t4f4f4f4f4": "Coinbase",
    "AC5RDfQFmDS1deWZosYb21bfU9a8hC7GPT8g82aJjX5J": "Kraken",
    "FWznbcNXWQu3oWjdwtnyHwrNVCcZq9Fzj7x8VbzY6b8X": "Kraken",
    "A77HErqxdUwXBH7q7rFx3t9qG8uFkqF8qF8qF8qF8qF8": "OKX",
    "31bsK5k13e1G9WkT9g1Wk13e1G9WkT9g1Wk13e1G9Wk": "KuCoin",
    "61bsK5k13e1G9WkT9g1Wk13e1G9WkT9g1Wk13e1G9Wk": "MEXC",
    "ASTyfSimeXGAXhdf81g7a7a7a7a7a7a7a7a7a7a7a7a": "FixedFloat",
    "HVh5HkW5j5X5k5Hk5W5j5X5k5Hk5W5j5X5k5Hk5W5j5": "Gate.io",
    "BYT3n3k3n3n3k3n3n3k3n3n3k3n3n3k3n3n3k3n3n3k": "Bybit",
    "B1tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG3tG": "Bitget",
    "HWy1jotHpo6UqeQxx49dpYYdQB887zx8mwE": "Wintermute",
}


@dataclass
class WalletFunding:
    """Wallet funding information."""
    wallet_address: str
    funding_source: str  # CEX name or "DEX" or wallet address
    funding_amount_sol: float
    funding_time: datetime
    funding_tx: str
    is_cex: bool


@dataclass 
class EnhancedTokenData:
    """Enhanced token data combining multiple sources."""
    address: str
    symbol: str
    name: str
    price_usd: Optional[float]
    market_cap: Optional[float]
    liquidity_usd: Optional[float]
    volume_24h: Optional[float]
    age_minutes: int
    holder_count: Optional[int]
    dex_name: str
    is_pump_fun: bool
    # Pair address for Axiom links
    pair_address: Optional[str] = None
    # Social links
    telegram: Optional[str] = None
    twitter: Optional[str] = None
    website: Optional[str] = None
    
    @property
    def mc_string(self) -> str:
        if not self.market_cap:
            return "?"
        mc = self.market_cap
        if mc >= 1_000_000:
            return f"{mc / 1_000_000:.1f}M"
        elif mc >= 1_000:
            return f"{mc / 1_000:.1f}k"
        return f"{mc:.0f}"
    
    @property
    def age_string(self) -> str:
        m = self.age_minutes
        if m < 60:
            return f"{m}m"
        elif m < 1440:
            return f"{m // 60}h"
        return f"{m // 1440}d"


class HeliusClient:
    """Helius enhanced API client with shared RPC rotation."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, rpc_url: str = None, rpc_manager=None):
        self.rpc_url = rpc_url
        self._rpc_manager = rpc_manager

    def _manager(self):
        if self._rpc_manager is None:
            self._rpc_manager = get_rpc_manager()
        return self._rpc_manager

    def _attempt_count(self) -> int:
        if self.rpc_url:
            return 1
        return max(1, getattr(self._manager(), "endpoint_count", 1))

    async def _post_rpc(self, client: httpx.AsyncClient, payload: dict, timeout: float | None = None):
        """Post a JSON-RPC request with endpoint rotation on provider failures."""
        manager = None if self.rpc_url else self._manager()
        last_response = None

        for _ in range(self._attempt_count()):
            rpc_url = self.rpc_url or manager.get_rpc_url()
            if timeout is None:
                response = await client.post(rpc_url, json=payload)
            else:
                response = await client.post(rpc_url, json=payload, timeout=timeout)

            last_response = response
            status_code = getattr(response, "status_code", 200)
            if status_code == 429 and manager is not None:
                manager.report_error(rpc_url, is_rate_limit=True)
                continue
            if status_code in self.RETRYABLE_STATUS_CODES and manager is not None:
                manager.report_error(rpc_url, is_rate_limit=False)
                continue
            return response

        return last_response

    async def get_wallet_funding(self, wallet_address: str) -> Optional[WalletFunding]:
        """
        Trace where a wallet's SOL came from.
        Returns funding source info.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [wallet_address, {"limit": 50}],
                }

                response = await self._post_rpc(client, payload)
                if not response or getattr(response, "status_code", 200) != 200:
                    return None
                result = response.json()
                signatures = result.get("result", [])

                if not signatures:
                    return None

                first_sig = signatures[-1]
                first_tx_time = datetime.fromtimestamp(first_sig.get("blockTime", 0))

                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        first_sig["signature"],
                        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                    ],
                }

                tx_response = await self._post_rpc(client, tx_payload)
                if not tx_response or getattr(tx_response, "status_code", 200) != 200:
                    return None
                tx_data = tx_response.json().get("result")

                if not tx_data:
                    return None

                account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
                pre_balances = tx_data.get("meta", {}).get("preBalances", [])
                post_balances = tx_data.get("meta", {}).get("postBalances", [])

                funding_source = "Unknown"
                funding_amount = 0
                is_cex = False

                for i, key in enumerate(account_keys):
                    if i >= len(pre_balances) or i >= len(post_balances):
                        continue
                    key_str = key.get("pubkey") if isinstance(key, dict) else key

                    if key_str == wallet_address:
                        if post_balances[i] > pre_balances[i]:
                            funding_amount = (post_balances[i] - pre_balances[i]) / 1e9
                    elif pre_balances[i] > post_balances[i]:
                        sent_amount = (pre_balances[i] - post_balances[i]) / 1e9
                        if sent_amount > 0.001:
                            if key_str in CEX_WALLETS:
                                funding_source = CEX_WALLETS[key_str]
                                is_cex = True
                            else:
                                funding_source = f"{key_str[:4]}...{key_str[-4:]}"

                return WalletFunding(
                    wallet_address=wallet_address,
                    funding_source=funding_source,
                    funding_amount_sol=funding_amount,
                    funding_time=first_tx_time,
                    funding_tx=first_sig["signature"],
                    is_cex=is_cex,
                )

        except Exception as e:
            logger.error(f"Error getting wallet funding: {e}")
            return None

    async def get_wallet_age_and_tx_count(self, wallet_address: str) -> tuple:
        """Get wallet age in days and transaction count."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [wallet_address, {"limit": 100}],
                }

                response = await self._post_rpc(client, payload)
                if not response or getattr(response, "status_code", 200) != 200:
                    return 0, 0
                result = response.json()
                signatures = result.get("result", [])

                if not signatures:
                    logger.debug(f"Wallet {wallet_address[:8]}... has 0 transactions")
                    return 0, 0

                tx_count = len(signatures)
                oldest = signatures[-1]
                first_tx_time = datetime.fromtimestamp(oldest.get("blockTime", 0))
                age_days = (datetime.utcnow() - first_tx_time).days

                logger.debug(f"Wallet {wallet_address[:8]}... - Age: {age_days}d, TXs: {tx_count}")
                return age_days, tx_count

        except Exception as e:
            logger.error(f"Error getting wallet age: {e}")
            return 0, 0

    async def is_fresh_wallet(self, wallet_address: str) -> bool:
        """Check if wallet qualifies as 'fresh'."""
        age_days, tx_count = await self.get_wallet_age_and_tx_count(wallet_address)
        return age_days <= settings.fresh_wallet_max_age_days and tx_count <= 50

    async def get_wallet_token_balance(self, wallet_address: str, token_mint: str) -> float:
        """Get a wallet's balance of a specific token."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        wallet_address,
                        {"mint": token_mint},
                        {"encoding": "jsonParsed"},
                    ],
                }

                response = await self._post_rpc(client, payload)
                if not response or getattr(response, "status_code", 200) != 200:
                    return 0.0
                result = response.json()
                accounts = result.get("result", {}).get("value", [])

                if not accounts:
                    return 0.0

                total_balance = 0.0
                for account in accounts:
                    parsed = account.get("account", {}).get("data", {}).get("parsed", {})
                    info = parsed.get("info", {})
                    token_amount = info.get("tokenAmount", {})
                    ui_amount = token_amount.get("uiAmount", 0) or 0
                    total_balance += ui_amount

                return total_balance

        except Exception as e:
            logger.debug(f"Error getting wallet token balance: {e}")
            return 0.0

# ==================== COMBINED DATA FETCHER ====================

class TokenDataFetcher:
    """Fetches and combines data from multiple free APIs."""
    
    def __init__(self):
        self.jupiter = JupiterClient()
        self.helius = HeliusClient()
        self._cache: Dict[str, EnhancedTokenData] = {}
    
    async def get_token_data(self, token_address: str) -> Optional[EnhancedTokenData]:
        """Fetch comprehensive token data from all sources with fallbacks."""
        
        # Check cache first
        if token_address in self._cache:
            cached = self._cache[token_address]
            # Cache for 2 minutes
            if hasattr(cached, '_cached_at'):
                cache_age = (datetime.utcnow() - cached._cached_at).total_seconds()
                if cache_age < 120:
                    return cached
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try DexScreener first
                token_data = await self._try_dexscreener(client, token_address)
                
                # If DexScreener failed, try pump.fun API for pump tokens
                if not token_data and token_address.endswith("pump"):
                    token_data = await self._try_pumpfun_api(client, token_address)
                
                # If still no data, try Helius token metadata
                if not token_data:
                    token_data = await self._try_helius_metadata(client, token_address)
                
                if token_data:
                    token_data._cached_at = datetime.utcnow()
                    self._cache[token_address] = token_data
                
                return token_data
                
        except Exception as e:
            logger.error(f"Error fetching token data: {e}")
            return None
    
    async def get_pair_address(self, token_address: str) -> Optional[str]:
        """
        Get the pair address for a token.
        1. For pump.fun tokens (ending in 'pump'), deterministically derive the bonding curve.
        2. For others, try DexScreener.
        """
        # 1. Deterministically derive pump.fun pair (bonding curve)
        if token_address.endswith("pump"):
            try:
                from solders.pubkey import Pubkey
                program_id = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
                mint = Pubkey.from_string(token_address)
                seeds = [b"bonding-curve", bytes(mint)]
                bonding_curve, _ = Pubkey.find_program_address(seeds, program_id)
                pair_address = str(bonding_curve)
                logger.debug(f"Derived pump.fun bonding curve for {token_address[:8]}: {pair_address}")
                return pair_address
            except ImportError:
                logger.warning("solders library not available for picking pump.fun pair")
            except Exception as e:
                logger.error(f"Error deriving pump.fun pair: {e}")

        # 2. Try DexScreener for other tokens
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
                    timeout=5.0
                )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                pairs = data.get("pairs", [])
                
                if not pairs:
                    return None
                
                # Get the most liquid pair (first one is usually highest liquidity)
                # Prefer Solana chain pairs
                for pair in pairs:
                    if pair.get("chainId") == "solana":
                        pair_address = pair.get("pairAddress")
                        if pair_address:
                            logger.debug(f"Found pair address for {token_address[:8]}: {pair_address[:8]}...")
                            return pair_address
                
                # If no Solana pair found, return first available pair
                if pairs[0].get("pairAddress"):
                    return pairs[0]["pairAddress"]
                
                return None
                
        except Exception as e:
            logger.debug(f"Error fetching pair address for {token_address[:8]}: {e}")
            return None
    
    async def _try_dexscreener(self, client: httpx.AsyncClient, token_address: str) -> Optional[EnhancedTokenData]:
        """Try fetching from DexScreener API."""
        try:
            response = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
                timeout=5.0
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                return None
            
            pair = pairs[0]
            base_token = pair.get("baseToken", {})
            
            # Parse age
            age_minutes = 0
            if pair.get("pairCreatedAt"):
                try:
                    created = datetime.fromtimestamp(pair["pairCreatedAt"] / 1000)
                    age_minutes = int((datetime.utcnow() - created).total_seconds() / 60)
                except:
                    pass
            
            # Get pair address for Axiom links
            pair_address = pair.get("pairAddress")
            
            # Check if pump.fun
            dex_name = pair.get("dexId", "unknown")
            is_pump = "pump" in dex_name.lower() or "pump" in pair.get("url", "").lower()
            
            # Extract social links
            info = pair.get("info", {})
            socials = info.get("socials", [])
            telegram_link = None
            twitter_link = None
            website_link = None
            
            for social in socials:
                if social.get("type") == "telegram":
                    telegram_link = social.get("url")
                elif social.get("type") == "twitter":
                    twitter_link = social.get("url")
            
            websites = info.get("websites", [])
            if websites:
                website_link = websites[0].get("url")
            
            return EnhancedTokenData(
                address=token_address,
                symbol=base_token.get("symbol", "???"),
                name=base_token.get("name", "Unknown"),
                price_usd=float(pair.get("priceUsd")) if pair.get("priceUsd") else None,
                market_cap=float(pair.get("marketCap")) if pair.get("marketCap") else None,
                liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)) if pair.get("liquidity") else None,
                volume_24h=float(pair.get("volume", {}).get("h24", 0)) if pair.get("volume") else None,
                age_minutes=age_minutes,
                holder_count=None,
                dex_name=dex_name,
                is_pump_fun=is_pump,
                pair_address=pair_address,
                telegram=telegram_link,
                twitter=twitter_link,
                website=website_link,
            )
        except Exception as e:
            logger.debug(f"DexScreener failed for {token_address[:8]}: {e}")
            return None
    
    async def _try_pumpfun_api(self, client: httpx.AsyncClient, token_address: str) -> Optional[EnhancedTokenData]:
        """Try fetching from pump.fun API for new pump tokens."""
        try:
            response = await client.get(
                f"https://frontend-api.pump.fun/coins/{token_address}",
                timeout=5.0
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if not data or not data.get("symbol"):
                return None
            
            # Calculate market cap from bonding curve if available
            market_cap = None
            if data.get("usd_market_cap"):
                market_cap = float(data["usd_market_cap"])
            elif data.get("market_cap"):
                market_cap = float(data["market_cap"])
            
            # Calculate age
            age_minutes = 0
            if data.get("created_timestamp"):
                try:
                    created = datetime.fromtimestamp(data["created_timestamp"] / 1000)
                    age_minutes = int((datetime.utcnow() - created).total_seconds() / 60)
                except:
                    pass
            
            logger.info(f"✅ Pump.fun API success: ${data.get('symbol')} {data.get('name')}")
            
            return EnhancedTokenData(
                address=token_address,
                symbol=data.get("symbol", "???"),
                name=data.get("name", "Unknown"),
                price_usd=None,  # pump.fun API doesn't always have price
                market_cap=market_cap,
                liquidity_usd=None,
                volume_24h=None,
                age_minutes=age_minutes,
                holder_count=None,
                dex_name="pump.fun",
                is_pump_fun=True,
            )
        except Exception as e:
            logger.debug(f"Pump.fun API failed for {token_address[:8]}: {e}")
            return None
    
    async def _try_helius_metadata(self, client: httpx.AsyncClient, token_address: str) -> Optional[EnhancedTokenData]:
        """Try fetching token metadata from Helius/Solana."""
        try:
            # Use Helius getAsset for metadata
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAsset",
                "params": {"id": token_address}
            }
            
            response = await self.helius._post_rpc(client, payload, timeout=5.0)
            if not response or getattr(response, "status_code", 200) != 200:
                return None
            
            result = response.json()
            asset = result.get("result")
            
            if not asset:
                return None
            
            content = asset.get("content", {})
            metadata = content.get("metadata", {})
            
            symbol = metadata.get("symbol", "???")
            name = metadata.get("name", "Unknown")
            
            # Check if it's actually a token with valid metadata
            if symbol == "???" and name == "Unknown":
                return None
            
            logger.info(f"✅ Helius metadata success: ${symbol} {name}")
            
            return EnhancedTokenData(
                address=token_address,
                symbol=symbol,
                name=name,
                price_usd=None,
                market_cap=None,
                liquidity_usd=None,
                volume_24h=None,
                age_minutes=0,
                holder_count=None,
                dex_name="unknown",
                is_pump_fun=token_address.endswith("pump"),
            )
        except Exception as e:
            logger.debug(f"Helius metadata failed for {token_address[:8]}: {e}")
            return None
    
    async def get_wallet_info(self, wallet_address: str) -> dict:
        """Get comprehensive wallet info."""
        funding = await self.helius.get_wallet_funding(wallet_address)
        age_days, tx_count = await self.helius.get_wallet_age_and_tx_count(wallet_address)
        
        is_fresh = age_days <= settings.fresh_wallet_max_age_days and tx_count <= 20
        
        # If funding source is unknown, show wallet abbreviation
        if funding and funding.funding_source != "Unknown":
            funding_source = funding.funding_source
        elif funding:
            # Show abbreviated wallet address that funded this wallet
            funding_source = f"{wallet_address[:4]}..{wallet_address[-4:]}"
        else:
            funding_source = f"{wallet_address[:4]}..{wallet_address[-4:]}"
        
        return {
            "address": wallet_address,
            "age_days": age_days,
            "tx_count": tx_count,
            "is_fresh": is_fresh,
            "funding_source": funding_source,
            "funding_time": funding.funding_time.strftime("%H:%M") if funding else "?",
            "is_cex_funded": funding.is_cex if funding else False,
        }


# Singletons
_jupiter: JupiterClient | None = None
_helius: HeliusClient | None = None
_fetcher: TokenDataFetcher | None = None


def get_jupiter_client() -> JupiterClient:
    global _jupiter
    if _jupiter is None:
        _jupiter = JupiterClient()
    return _jupiter


def get_helius_client() -> HeliusClient:
    global _helius
    if _helius is None:
        _helius = HeliusClient()
    return _helius


def get_token_fetcher() -> TokenDataFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = TokenDataFetcher()
    return _fetcher
