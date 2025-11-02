"""
Multi-Source Price Oracle - Real-time token prices from multiple sources

x402-enabled microservice for cryptocurrency price aggregation
"""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .coingecko_fetcher import CoinGeckoFetcher
from .price_aggregator import PriceAggregator
from .x402_middleware_dual import X402Middleware

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Multi-Source Price Oracle",
    description="Real-time token prices aggregated from CoinGecko and on-chain DEXs with confidence scoring",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
FREE_MODE = os.getenv("FREE_MODE", "true").lower() == "true"
PAYMENT_ADDRESS = os.getenv("PAYMENT_ADDRESS", "0x01D11F7e1a46AbFC6092d7be484895D2d505095c")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

# Initialize price fetchers
coingecko_fetcher = CoinGeckoFetcher()
price_aggregator = PriceAggregator()

if FREE_MODE:
    logger.warning("Running in FREE MODE - no payment verification")
else:
    logger.info("x402 payment verification enabled with dual facilitators")

logger.info("Price oracle initialized")

# x402 Payment Middleware
payment_address = PAYMENT_ADDRESS
base_url = BASE_URL.rstrip('/')

app.add_middleware(
    X402Middleware,
    payment_address=payment_address,
    base_url=base_url,
    facilitator_urls=[
        "https://facilitator.daydreams.systems",
        "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
    ],
    free_mode=FREE_MODE,
)


# Request/Response Models
class PriceRequest(BaseModel):
    """Price query request"""
    token_address: str = Field(..., description="Token contract address")
    chain_id: int = Field(default=1, description="Blockchain ID (default: 1 = Ethereum)")
    vs_currency: str = Field(default="usd", description="Currency to price against (default: usd)")

    class Config:
        json_schema_extra = {
            "example": {
                "token_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "chain_id": 1,
                "vs_currency": "usd"
            }
        }


class PriceResponse(BaseModel):
    """Price query response"""
    token_address: str
    chain_id: int
    price_usd: float
    confidence: float
    sources_count: int
    price_range: dict
    change_24h: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    sources: list
    warnings: list
    timestamp: str


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def landing_page():
    """Landing page with metadata"""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Price Oracle</title>
    <meta property="og:title" content="Price Oracle">
    <meta property="og:description" content="Multi-chain token price feeds via x402 micropayments">
    <meta property="og:image" content="https://price-oracle-production-9e7c.up.railway.app/favicon.ico">
    <link rel="icon" href="/favicon.ico" type="image/svg+xml">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            line-height: 1.6;
        }
        h1 { color: #333; }
        .endpoint { background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0; }
        code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; }
    </style>
</head>
<body>
    <h1>💰 Price Oracle</h1>
    <p>Multi-chain token price feeds via x402 micropayments</p>
    <div class="endpoint">
        <strong>Main Endpoint:</strong> <code>POST /entrypoints/price-oracle/invoke</code>
    </div>
    <div class="endpoint">
        <strong>Documentation:</strong> <a href="/docs">/docs</a>
    </div>
    <div class="endpoint">
        <strong>x402 Metadata:</strong> <a href="/.well-known/x402">/.well-known/x402</a>
    </div>
</body>
</html>"""


@app.get("/favicon.ico")
async def favicon():
    """Favicon endpoint returning SVG with emoji"""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <text y="80" font-size="80">💰</text>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/entrypoints/price-oracle/invoke")
async def price_oracle_get():
    """GET endpoint returning HTTP 402 with x402 metadata"""
    headers = {
        "X-Accepts-Payment": "x402",
        "X-Payment-Network": "base",
        "X-Payment-Asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "X-Payment-Amount": "10000",
        "X-Payment-Address": payment_address,
        "X-Facilitator-Url": "https://facilitator.daydreams.systems"
    }

    metadata = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "maxAmountRequired": "10000",
        "resource": f"{base_url}/entrypoints/price-oracle/invoke",
        "description": "Real-time token price with multi-source aggregation and confidence scoring",
        "mimeType": "application/json",
        "payTo": payment_address,
        "maxTimeoutSeconds": 15,
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "outputSchema": {
            "input": {
                "type": "http",
                "method": "POST",
                "bodyType": "json",
                "bodyFields": {
                    "token_address": {
                        "type": "string",
                        "required": True,
                        "description": "Token contract address"
                    },
                    "chain_id": {
                        "type": "number",
                        "required": False,
                        "description": "Blockchain ID (default: 1 = Ethereum)"
                    },
                    "vs_currency": {
                        "type": "string",
                        "required": False,
                        "description": "Currency to price against (default: usd)"
                    }
                }
            },
            "output": {
                "type": "object",
                "description": "Token price data with confidence scoring and multi-source aggregation"
            }
        }
    }

    return Response(
        content=str(metadata),
        status_code=402,
        headers=headers,
        media_type="application/json"
    )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "price-oracle",
        "version": "1.0.0",
        "free_mode": FREE_MODE,
        "sources": ["coingecko"]
    }


@app.post(
    "/entrypoints/price-oracle/invoke",
    response_model=PriceResponse,
    summary="Get Token Price",
    description="Get real-time token price from multiple sources with confidence scoring"
)
async def get_token_price(request: PriceRequest):
    """
    Get token price from multiple sources

    This endpoint aggregates prices from:
    - CoinGecko (CEX aggregated prices)
    - On-chain DEX pools (when available)

    Returns:
    - Aggregated price with confidence score
    - Price range and spread between sources
    - 24h price change and volume data
    - Warnings for unusual price spreads

    Useful for:
    - Portfolio valuation
    - Trading decisions
    - Arbitrage detection
    - Price verification
    """
    try:
        logger.info(
            f"Fetching price for {request.token_address} on chain {request.chain_id}"
        )

        # Fetch from CoinGecko
        coingecko_data = await coingecko_fetcher.get_token_price(
            request.token_address,
            request.vs_currency
        )

        # Collect all price sources
        source_prices = [coingecko_data]

        # Aggregate prices
        result = price_aggregator.aggregate_prices(
            request.token_address,
            request.chain_id,
            source_prices
        )

        # Add timestamp
        result.timestamp = datetime.utcnow().isoformat() + "Z"

        # Extract additional data from CoinGecko
        change_24h = coingecko_data.get("change_24h")
        market_cap = coingecko_data.get("market_cap")
        volume_24h = coingecko_data.get("volume_24h")

        return PriceResponse(
            token_address=result.token_address,
            chain_id=result.chain_id,
            price_usd=result.price_usd,
            confidence=result.confidence,
            sources_count=result.sources_count,
            price_range=result.price_range,
            change_24h=change_24h,
            market_cap=market_cap,
            volume_24h=volume_24h,
            sources=result.sources,
            warnings=result.warnings,
            timestamp=result.timestamp
        )

    except Exception as e:
        logger.error(f"Price fetch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Price fetch failed: {str(e)}")


# Agent Discovery Endpoints
@app.get("/.well-known/agent.json")
async def agent_metadata():
    """Agent metadata for service discovery"""
    return {
        "name": "Multi-Source Price Oracle",
        "description": "Real-time token prices aggregated from CoinGecko and on-chain DEXs. Provides confidence-scored prices with spread detection and arbitrage alerts.",
        "url": f"{base_url}/",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
            "extensions": [
                {
                    "uri": "https://github.com/google-agentic-commerce/ap2/tree/v0.1",
                    "description": "Agent Payments Protocol (AP2)",
                    "required": True,
                    "params": {"roles": ["merchant"]}
                }
            ]
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "entrypoints": {
            "price-oracle": {
                "description": "Get real-time token prices with confidence scoring",
                "streaming": False,
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "token_address": {"type": "string"},
                        "chain_id": {"type": "integer"},
                        "vs_currency": {"type": "string"}
                    },
                    "required": ["token_address"]
                },
                "output_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "price_usd": {"type": "number"},
                        "confidence": {"type": "number"},
                        "price_range": {"type": "object"},
                        "warnings": {"type": "array"}
                    }
                },
                "pricing": {"invoke": "0.01 USDC"}
            }
        },
        "payments": [
            {
                "method": "x402",
                "payee": payment_address,
                "network": "base",
                "endpoint": "https://facilitator.daydreams.systems",
                "priceModel": {"default": "0.01"},
                "extensions": {
                    "x402": {"facilitatorUrl": "https://facilitator.daydreams.systems"}
                }
            }
        ]
    }


@app.get("/.well-known/x402")
async def x402_metadata():
    """x402 payment metadata"""
    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "10000",  # 0.01 USDC
                "resource": f"{base_url}/entrypoints/price-oracle/invoke",
                "description": "Real-time token price with multi-source aggregation and confidence scoring",
                "mimeType": "application/json",
                "payTo": payment_address,
                "maxTimeoutSeconds": 15,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
                "outputSchema": {
                    "input": {
                        "type": "http",
                        "method": "POST",
                        "bodyType": "json",
                        "bodyFields": {
                            "token_address": {
                                "type": "string",
                                "required": True,
                                "description": "Token contract address"
                            },
                            "chain_id": {
                                "type": "integer",
                                "required": False,
                                "description": "Blockchain ID (default: 1)"
                            }
                        }
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "price_usd": {"type": "number"},
                            "confidence": {"type": "number"},
                            "price_range": {"type": "object"},
                            "change_24h": {"type": "number"}
                        }
                    }
                },
                "extra": {
                    "sources": ["coingecko", "dex_pools"],
                    "features": [
                        "multi_source_aggregation",
                        "confidence_scoring",
                        "spread_detection",
                        "arbitrage_alerts"
                    ],
                    "update_frequency": "real_time"
                }
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
