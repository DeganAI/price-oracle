"""
Price Aggregator - Combines multiple price sources with confidence scoring
"""
import logging
from typing import Dict, List
from statistics import median, stdev
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PriceResult:
    """Aggregated price result"""
    token_address: str
    chain_id: int
    price_usd: float
    confidence: float  # 0.0-1.0
    sources_count: int
    price_range: Dict  # min, max, spread
    sources: List[Dict]
    warnings: List[str]
    timestamp: str


class PriceAggregator:
    """Aggregate prices from multiple sources with confidence scoring"""

    # Maximum acceptable price spread between sources (%)
    MAX_SPREAD_PCT = 5.0

    def aggregate_prices(
        self,
        token_address: str,
        chain_id: int,
        source_prices: List[Dict]
    ) -> PriceResult:
        """
        Aggregate prices from multiple sources

        Args:
            token_address: Token contract address
            chain_id: Blockchain ID
            source_prices: List of price data from different sources

        Returns:
            PriceResult with aggregated price and confidence
        """
        # Filter out failed sources
        valid_sources = [
            s for s in source_prices
            if s.get("price_usd") is not None and s.get("price_usd") > 0
        ]

        if not valid_sources:
            # No valid prices
            return self._create_error_result(
                token_address,
                chain_id,
                "No valid price sources available",
                source_prices
            )

        # Extract prices and confidences
        prices = [s["price_usd"] for s in valid_sources]
        confidences = [s.get("confidence", 0.5) for s in valid_sources]

        # Calculate price statistics
        if len(prices) == 1:
            # Single source
            final_price = prices[0]
            price_min = prices[0]
            price_max = prices[0]
            spread_pct = 0.0
            confidence = confidences[0] * 0.8  # Reduce confidence for single source
        else:
            # Multiple sources - use weighted average or median
            final_price = self._calculate_weighted_price(prices, confidences)
            price_min = min(prices)
            price_max = max(prices)
            spread_pct = ((price_max - price_min) / final_price) * 100 if final_price > 0 else 0
            confidence = self._calculate_confidence(prices, confidences, spread_pct)

        # Generate warnings
        warnings = self._generate_warnings(spread_pct, len(valid_sources), len(source_prices))

        return PriceResult(
            token_address=token_address,
            chain_id=chain_id,
            price_usd=round(final_price, 6),
            confidence=round(confidence, 3),
            sources_count=len(valid_sources),
            price_range={
                "min": round(price_min, 6),
                "max": round(price_max, 6),
                "spread_percent": round(spread_pct, 2)
            },
            sources=valid_sources,
            warnings=warnings,
            timestamp=""  # Will be set by caller
        )

    def _calculate_weighted_price(
        self,
        prices: List[float],
        confidences: List[float]
    ) -> float:
        """Calculate weighted average price based on source confidence"""
        if not prices:
            return 0.0

        # Weight each price by its confidence
        weighted_sum = sum(p * c for p, c in zip(prices, confidences))
        total_weight = sum(confidences)

        if total_weight == 0:
            return median(prices)  # Fallback to median

        return weighted_sum / total_weight

    def _calculate_confidence(
        self,
        prices: List[float],
        confidences: List[float],
        spread_pct: float
    ) -> float:
        """
        Calculate overall confidence in the price

        Higher confidence when:
        - Multiple sources agree
        - Low price spread
        - High individual source confidences
        """
        base_confidence = median(confidences)

        # Adjust for number of sources
        source_bonus = min(0.1 * len(prices), 0.2)  # Up to +0.2 for multiple sources

        # Penalize for high spread
        if spread_pct > self.MAX_SPREAD_PCT:
            spread_penalty = min((spread_pct - self.MAX_SPREAD_PCT) / 100, 0.3)
        else:
            spread_penalty = 0

        # Calculate final confidence
        confidence = base_confidence + source_bonus - spread_penalty

        return max(0.1, min(1.0, confidence))  # Clamp between 0.1 and 1.0

    def _generate_warnings(
        self,
        spread_pct: float,
        valid_sources: int,
        total_sources: int
    ) -> List[str]:
        """Generate warnings based on price data quality"""
        warnings = []

        if spread_pct > self.MAX_SPREAD_PCT:
            warnings.append(
                f"⚠️ High price spread: {spread_pct:.1f}% between sources"
            )

        if spread_pct > 15:
            warnings.append(
                "🚨 VERY HIGH SPREAD - Price may be unreliable or arbitrage opportunity"
            )

        if valid_sources == 1:
            warnings.append(
                "ℹ️ Single price source - confidence reduced"
            )

        if valid_sources < total_sources:
            failed = total_sources - valid_sources
            warnings.append(
                f"ℹ️ {failed} source(s) failed to provide price"
            )

        if valid_sources == 0:
            warnings.append(
                "🚫 No valid price data available"
            )

        return warnings

    def _create_error_result(
        self,
        token_address: str,
        chain_id: int,
        error_msg: str,
        source_prices: List[Dict]
    ) -> PriceResult:
        """Create error result when no valid prices available"""
        return PriceResult(
            token_address=token_address,
            chain_id=chain_id,
            price_usd=0.0,
            confidence=0.0,
            sources_count=0,
            price_range={"min": 0, "max": 0, "spread_percent": 0},
            sources=source_prices,
            warnings=[f"🚫 {error_msg}"],
            timestamp=""
        )
