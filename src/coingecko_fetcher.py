"""
CoinGecko Price Fetcher - CEX aggregated prices
"""
import logging
import aiohttp
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CoinGeckoFetcher:
    """Fetch token prices from CoinGecko API (free tier, no API key)"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    # Common token ID mappings
    TOKEN_IDS = {
        # Ethereum
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": "weth",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": "usd-coin",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": "tether",
        "0x6B175474E89094C44Da98b954EedeAC495271d0F": "dai",
        "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": "wrapped-bitcoin",
        "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984": "uniswap",
        "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9": "aave",
        "0x514910771AF9Ca656af840dff83E8264EcF986CA": "chainlink",
        # Add more as needed
    }

    async def get_token_price(
        self,
        token_address: str,
        vs_currency: str = "usd"
    ) -> Dict:
        """
        Get token price from CoinGecko

        Args:
            token_address: Token contract address
            vs_currency: Currency to price against (default: usd)

        Returns:
            Dict with price data or error
        """
        try:
            token_address = token_address.lower()

            # Try to map to CoinGecko ID
            token_id = self.TOKEN_IDS.get(token_address)

            if token_id:
                # Use simple price endpoint for known tokens
                return await self._get_simple_price(token_id, vs_currency)
            else:
                # Use contract address lookup for unknown tokens
                return await self._get_contract_price(token_address, vs_currency)

        except Exception as e:
            logger.error(f"CoinGecko fetch error: {e}")
            return {
                "source": "coingecko",
                "error": str(e),
                "price_usd": None
            }

    async def _get_simple_price(
        self,
        token_id: str,
        vs_currency: str
    ) -> Dict:
        """Get price using token ID (faster, more reliable)"""
        url = f"{self.BASE_URL}/simple/price"
        params = {
            "ids": token_id,
            "vs_currencies": vs_currency,
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()

                    if token_id in data and vs_currency in data[token_id]:
                        token_data = data[token_id]
                        return {
                            "source": "coingecko",
                            "method": "simple_price",
                            "token_id": token_id,
                            "price_usd": token_data.get(vs_currency),
                            "change_24h": token_data.get(f"{vs_currency}_24h_change"),
                            "market_cap": token_data.get(f"{vs_currency}_market_cap"),
                            "volume_24h": token_data.get(f"{vs_currency}_24h_vol"),
                            "confidence": 0.95  # High confidence for known tokens
                        }

                logger.warning(f"CoinGecko API returned {response.status}")
                return {
                    "source": "coingecko",
                    "error": f"API returned {response.status}",
                    "price_usd": None
                }

    async def _get_contract_price(
        self,
        contract_address: str,
        vs_currency: str
    ) -> Dict:
        """Get price using contract address (for unknown tokens)"""
        # Try Ethereum first (most common)
        url = f"{self.BASE_URL}/simple/token_price/ethereum"
        params = {
            "contract_addresses": contract_address,
            "vs_currencies": vs_currency,
            "include_24hr_change": "true"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()

                    if contract_address in data and vs_currency in data[contract_address]:
                        token_data = data[contract_address]
                        return {
                            "source": "coingecko",
                            "method": "contract_price",
                            "contract_address": contract_address,
                            "price_usd": token_data.get(vs_currency),
                            "change_24h": token_data.get(f"{vs_currency}_24h_change"),
                            "confidence": 0.85  # Slightly lower confidence for contract lookup
                        }

                # Token not found on Ethereum, might be on another chain
                return {
                    "source": "coingecko",
                    "error": "Token not found on CoinGecko",
                    "price_usd": None
                }
