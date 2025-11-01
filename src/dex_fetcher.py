"""
DEX Price Fetcher - On-chain prices from Uniswap and other DEXs
"""
import logging
from typing import Dict, Optional
from web3 import Web3
from decimal import Decimal

logger = logging.getLogger(__name__)


class DEXFetcher:
    """Fetch token prices directly from DEX pools"""

    # Uniswap V2 Pair ABI (minimal)
    PAIR_ABI = [
        {
            "constant": True,
            "inputs": [],
            "name": "getReserves",
            "outputs": [
                {"name": "reserve0", "type": "uint112"},
                {"name": "reserve1", "type": "uint112"},
                {"name": "blockTimestampLast", "type": "uint32"}
            ],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        }
    ]

    # Common stablecoin addresses (for pricing)
    STABLECOINS = {
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": {"symbol": "USDC", "decimals": 6},  # USDC
        "0xdAC17F958D2ee523a2206206994597C13D831ec7": {"symbol": "USDT", "decimals": 6},  # USDT
        "0x6B175474E89094C44Da98b954EedeAC495271d0F": {"symbol": "DAI", "decimals": 18},  # DAI
    }

    # WETH address (for ETH pricing)
    WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    def __init__(self, w3_instances: Dict[int, Web3]):
        """
        Initialize with Web3 instances

        Args:
            w3_instances: Dict mapping chain_id to Web3 instance
        """
        self.w3_instances = w3_instances

    async def get_token_price(
        self,
        token_address: str,
        chain_id: int,
        pair_address: Optional[str] = None
    ) -> Dict:
        """
        Get token price from DEX pool

        Args:
            token_address: Token contract address
            chain_id: Blockchain ID
            pair_address: Optional specific pair address to use

        Returns:
            Dict with price data or error
        """
        try:
            w3 = self.w3_instances.get(chain_id)
            if not w3:
                return {
                    "source": "dex",
                    "error": f"Chain {chain_id} not supported",
                    "price_usd": None
                }

            token_address = token_address.lower()

            # If pair address provided, use it directly
            if pair_address:
                return await self._get_pair_price(w3, token_address, pair_address)

            # Otherwise, this would require finding the best pair
            # For now, return unsupported
            return {
                "source": "dex",
                "error": "Pair address required for DEX pricing",
                "price_usd": None
            }

        except Exception as e:
            logger.error(f"DEX fetch error: {e}")
            return {
                "source": "dex",
                "error": str(e),
                "price_usd": None
            }

    async def _get_pair_price(
        self,
        w3: Web3,
        token_address: str,
        pair_address: str
    ) -> Dict:
        """Get price from a specific Uniswap V2 style pair"""
        try:
            pair_contract = w3.eth.contract(
                address=w3.to_checksum_address(pair_address),
                abi=self.PAIR_ABI
            )

            # Get reserves
            reserves = pair_contract.functions.getReserves().call()
            reserve0 = reserves[0]
            reserve1 = reserves[1]

            # Get token addresses
            token0 = pair_contract.functions.token0().call().lower()
            token1 = pair_contract.functions.token1().call().lower()

            # Determine which token is which
            if token_address == token0:
                token_reserve = reserve0
                quote_reserve = reserve1
                quote_token = token1
            elif token_address == token1:
                token_reserve = reserve1
                quote_reserve = reserve0
                quote_token = token0
            else:
                return {
                    "source": "dex",
                    "error": "Token not in pair",
                    "price_usd": None
                }

            # Calculate price (quote per token)
            if token_reserve == 0:
                return {
                    "source": "dex",
                    "error": "Zero liquidity",
                    "price_usd": None
                }

            # Simple price calculation
            # price = quote_reserve / token_reserve
            # This gives price in terms of quote token
            price_in_quote = Decimal(quote_reserve) / Decimal(token_reserve)

            # Check if quote token is a stablecoin
            quote_token_lower = quote_token.lower()
            if quote_token_lower in [k.lower() for k in self.STABLECOINS.keys()]:
                # Direct USD price
                price_usd = float(price_in_quote)
                confidence = 0.90

            elif quote_token_lower == self.WETH.lower():
                # Price in ETH, need to convert to USD
                # For now, use rough estimate
                eth_price = 3000  # TODO: Get actual ETH price
                price_usd = float(price_in_quote) * eth_price
                confidence = 0.75  # Lower confidence without actual ETH price

            else:
                # Unknown quote token
                return {
                    "source": "dex",
                    "error": "Unknown quote token",
                    "price_usd": None
                }

            return {
                "source": "dex",
                "method": "uniswap_v2_pair",
                "pair_address": pair_address,
                "token_address": token_address,
                "quote_token": quote_token,
                "price_usd": price_usd,
                "liquidity": {
                    "token_reserve": int(token_reserve),
                    "quote_reserve": int(quote_reserve)
                },
                "confidence": confidence
            }

        except Exception as e:
            logger.error(f"Pair price fetch error: {e}")
            return {
                "source": "dex",
                "error": f"Pair fetch failed: {str(e)}",
                "price_usd": None
            }
