"""Skopaq unified market data pipeline.

Provides native ingestion for Indian equities via INDstocks, automatic fallback
to Yahoo Finance with .NS suffix formatting, multi-tier caching, and typed models.
"""

from skopaq.data.models import (
    CompanyFundamentals,
    NewsArticle,
    QuoteData,
    validate_ohlcv_dataframe,
)
from skopaq.data.pipeline import (
    MarketDataError,
    UnifiedMarketData,
    get_fundamentals,
    get_historical_ohlcv,
    get_news,
    get_quote,
    get_stock_data,
    get_unified_market_data,
)
from skopaq.data.symbols import (
    detect_exchange,
    normalize_symbol,
    to_indstocks_symbol,
    to_yfinance_symbol,
)

__all__ = [
    "CompanyFundamentals",
    "NewsArticle",
    "QuoteData",
    "validate_ohlcv_dataframe",
    "MarketDataError",
    "UnifiedMarketData",
    "get_fundamentals",
    "get_historical_ohlcv",
    "get_news",
    "get_quote",
    "get_stock_data",
    "get_unified_market_data",
    "detect_exchange",
    "normalize_symbol",
    "to_indstocks_symbol",
    "to_yfinance_symbol",
]
