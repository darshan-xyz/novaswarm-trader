"""Unified Market Data Pipeline with transparent caching and automatic fallback."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Union
import pandas as pd

from novaswarm.config import NovaSwarmConfig
from novaswarm.data.indstocks import INDstocksDataProvider
from novaswarm.data.models import (
    QuoteData,
    CompanyFundamentals,
    NewsArticle,
    validate_ohlcv_dataframe,
)
from novaswarm.data.symbols import normalize_symbol, detect_exchange, to_yfinance_symbol
from novaswarm.data.yfinance import YFinanceDataProvider

logger = logging.getLogger(__name__)


class MarketDataError(Exception):
    """Raised when all configured data providers fail."""


class UnifiedMarketData:
    """Unified facade for all market data ingestion across NovaSwarm Trader.

    Features:
    - Primary Indian market ingestion via INDstocks.
    - Automatic transparent fallback to yfinance with .NS suffix handling.
    - Tier 1: In-memory TTL caching for Quotes, Fundamentals, and News.
    - Tier 2: Persistent disk caching for immutable historical daily candles.
    - Clean pandas DataFrame output for Technical Indicator engine.
    - Text formatting adapters for LLM agent prompt consumption.
    """

    def __init__(
        self,
        config: Optional[NovaSwarmConfig] = None,
        cache_dir: Optional[Union[str, Path]] = None,
    ):
        self.config = config or NovaSwarmConfig()
        self.cache_dir = Path(cache_dir or Path.home() / ".novaswarm" / "cache" / "market_data")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._indstocks = INDstocksDataProvider(self.config)
        self._yfinance = YFinanceDataProvider()

        # In-memory TTL caches
        self._quote_cache: dict[str, tuple[float, QuoteData]] = {}
        self._fundamentals_cache: dict[str, tuple[float, CompanyFundamentals]] = {}
        self._news_cache: dict[str, tuple[float, List[NewsArticle]]] = {}

        self.QUOTE_TTL = 10.0            # 10 seconds
        self.FUNDAMENTALS_TTL = 43200.0  # 12 hours
        self.NEWS_TTL = 1800.0           # 30 minutes

    @property
    def indstocks_provider(self) -> INDstocksDataProvider:
        """Provider instance for INDstocks."""
        return self._indstocks

    @property
    def yfinance_provider(self) -> YFinanceDataProvider:
        """Provider instance for yfinance."""
        return self._yfinance

    def _get_indstocks_token(self) -> str:
        """Safely extract INDstocks broker token across SecretStr, str, or None."""
        tok = getattr(self.config, "indstocks_token", None)
        if tok is None:
            return ""
        if hasattr(tok, "get_secret_value"):
            return tok.get_secret_value()
        return str(tok) if tok else ""

    # ── Historical OHLCV ────────────────────────────────────────────────

    def get_historical_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1day",
    ) -> pd.DataFrame:
        """Retrieve historical OHLCV DataFrame with transparent caching and fallback."""
        if start_date > end_date:
            raise ValueError(f"start_date must be before end_date: {start_date} > {end_date}")

        clean_sym = normalize_symbol(symbol)
        safe_sym = re.sub(r"[^A-Za-z0-9_-]", "_", clean_sym)
        if not safe_sym.strip("_"):
            safe_sym = "UNKNOWN"
        cache_file = (self.cache_dir / f"{safe_sym}_{interval}_{start_date}_{end_date}.parquet").resolve()

        # Check Tier 2 persistent cache
        if cache_file.exists():
            try:
                cached_df = pd.read_parquet(cache_file)
                return validate_ohlcv_dataframe(cached_df, symbol=clean_sym)
            except Exception as e:
                logger.debug("Failed to read cached parquet for %s: %s", clean_sym, e)

        df: Optional[pd.DataFrame] = None
        market = detect_exchange(symbol)

        # Attempt 1: INDstocks (Primary for Indian equities)
        token_val = self._get_indstocks_token()
        if market in ("NSE", "BSE") and token_val:
            try:
                df = self.indstocks_provider.get_historical(clean_sym, start_date, end_date, interval)
                if df is not None and not df.empty:
                    logger.debug("Successfully fetched %s historical from INDstocks", clean_sym)
                else:
                    df = None
            except Exception as exc:
                logger.warning(
                    "INDstocks historical fetch failed for %s (%s). Falling back to yfinance.",
                    clean_sym, exc,
                )
                df = None

        # Attempt 2: yfinance (Fallback for Indian equities, Primary for Global)
        if df is None or df.empty:
            try:
                yf_sym = to_yfinance_symbol(symbol)
                yf_interval = "1d" if interval in ("1day", "1d") else interval
                df = self.yfinance_provider.get_historical(yf_sym, start_date, end_date, yf_interval)
                if df is not None and not df.empty:
                    logger.debug("Successfully fetched %s historical from yfinance", yf_sym)
                else:
                    df = None
            except Exception as exc:
                logger.error("yfinance historical fetch failed for %s: %s", symbol, exc)
                df = None

        if df is None or df.empty:
            raise MarketDataError(f"Failed to retrieve OHLCV for '{clean_sym}' from all providers")

        # Save to Tier 2 persistent cache
        try:
            df.to_parquet(cache_file)
        except Exception as e:
            logger.debug("Failed writing parquet cache for %s: %s", clean_sym, e)

        return df

    # ── Live Quotes ──────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> QuoteData:
        """Retrieve real-time market quote with in-memory TTL caching."""
        clean_sym = normalize_symbol(symbol)
        now = time.time()

        # Check in-memory cache
        if clean_sym in self._quote_cache:
            ts, quote = self._quote_cache[clean_sym]
            if (now - ts) < self.QUOTE_TTL:
                return quote

        quote: Optional[QuoteData] = None
        market = detect_exchange(symbol)

        # Attempt 1: INDstocks (Primary for Indian equities)
        token_val = self._get_indstocks_token()
        if market in ("NSE", "BSE") and token_val:
            try:
                quote = self.indstocks_provider.get_quote(clean_sym)
            except Exception as exc:
                logger.warning("INDstocks quote failed for %s (%s). Falling back to yfinance.", clean_sym, exc)
                quote = None

        # Attempt 2: yfinance (Fallback)
        if quote is None:
            try:
                yf_sym = to_yfinance_symbol(symbol)
                quote = self.yfinance_provider.get_quote(yf_sym)
            except Exception as exc:
                raise MarketDataError(f"Failed to fetch quote for '{clean_sym}' from all providers: {exc}") from exc

        self._quote_cache[clean_sym] = (now, quote)
        return quote

    # ── Fundamentals ────────────────────────────────────────────────────

    def get_fundamentals(self, symbol: str) -> CompanyFundamentals:
        """Retrieve company fundamentals overview."""
        clean_sym = normalize_symbol(symbol)
        now = time.time()

        if clean_sym in self._fundamentals_cache:
            ts, data = self._fundamentals_cache[clean_sym]
            if (now - ts) < self.FUNDAMENTALS_TTL:
                return data

        try:
            yf_sym = to_yfinance_symbol(symbol)
            fundamentals = self.yfinance_provider.get_fundamentals(yf_sym)
        except Exception as exc:
            raise MarketDataError(f"Failed to retrieve fundamentals for '{clean_sym}': {exc}") from exc

        self._fundamentals_cache[clean_sym] = (now, fundamentals)
        return fundamentals

    # ── News ─────────────────────────────────────────────────────────────

    def get_news(
        self,
        symbol: str,
        curr_date: Optional[str] = None,
        look_back_days: int = 7,
    ) -> List[NewsArticle]:
        """Retrieve company news articles."""
        clean_sym = normalize_symbol(symbol)
        now = time.time()

        if clean_sym in self._news_cache:
            ts, articles = self._news_cache[clean_sym]
            if (now - ts) < self.NEWS_TTL:
                return articles

        try:
            yf_sym = to_yfinance_symbol(symbol)
            articles = self.yfinance_provider.get_news(yf_sym, limit=10)
            self._news_cache[clean_sym] = (now, articles)
            return articles
        except Exception as exc:
            logger.warning("News fetch failed for %s: %s", clean_sym, exc)
            return []

    # ── Backward Compatibility String Adapters ──────────────────────────

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        """String formatter for historical stock data export."""
        df = self.get_historical_ohlcv(symbol, start_date, end_date)
        header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Retrieved on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        return header + df.to_csv()


# Singleton instance and convenience functions
_default_pipeline: Optional[UnifiedMarketData] = None


def get_unified_market_data() -> UnifiedMarketData:
    """Get or create singleton UnifiedMarketData instance."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = UnifiedMarketData()
    return _default_pipeline


def get_historical_ohlcv(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = "1day",
) -> pd.DataFrame:
    """Fetch historical OHLCV data using the default pipeline."""
    return get_unified_market_data().get_historical_ohlcv(symbol, start_date, end_date, interval)


def get_quote(symbol: str) -> QuoteData:
    """Fetch live quote using the default pipeline."""
    return get_unified_market_data().get_quote(symbol)


def get_fundamentals(symbol: str) -> CompanyFundamentals:
    """Fetch fundamentals using the default pipeline."""
    return get_unified_market_data().get_fundamentals(symbol)


def get_news(
    symbol: str,
    curr_date: Optional[str] = None,
    look_back_days: int = 7,
) -> List[NewsArticle]:
    """Fetch news using the default pipeline."""
    return get_unified_market_data().get_news(symbol, curr_date, look_back_days)


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Fetch stock data CSV string using the default pipeline."""
    return get_unified_market_data().get_stock_data(symbol, start_date, end_date)
