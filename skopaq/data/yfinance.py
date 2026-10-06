"""Fallback market data provider via yfinance with automatic .NS suffix handling."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional, List
import pandas as pd
import yfinance as yf

from skopaq.data.models import (
    QuoteData,
    CompanyFundamentals,
    NewsArticle,
    validate_ohlcv_dataframe,
)
from skopaq.data.symbols import to_yfinance_symbol

logger = logging.getLogger(__name__)


def _clean_float(val, fallback: float = 0.0) -> float:
    """Safely convert value to float, handling None, NaN, and conversion errors."""
    if val is None or pd.isna(val):
        return float(fallback)
    try:
        f = float(val)
        return float(fallback) if pd.isna(f) else f
    except (ValueError, TypeError):
        return float(fallback)


class YFinanceError(Exception):
    """Base error for yfinance operations."""


class YFinanceDataProvider:
    """Robust provider wrapping Yahoo Finance with retries and format normalization."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _execute_with_retry(self, fn, *args, **kwargs):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
        raise YFinanceError(f"yfinance operation failed after {self.max_retries} attempts: {last_exc}") from last_exc

    def get_historical_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data with automatic .NS suffix formatting."""
        yf_symbol = to_yfinance_symbol(symbol)

        # Map common interval formats to valid yfinance interval tokens
        interval_map = {
            "1day": "1d",
            "1min": "1m",
            "1minute": "1m",
            "5min": "5m",
            "5minute": "5m",
            "15min": "15m",
            "15minute": "15m",
            "30min": "30m",
            "30minute": "30m",
            "60min": "1h",
            "60minute": "1h",
            "1hour": "1h",
            "1week": "1wk",
            "1month": "1mo",
        }
        yf_interval = interval_map.get(str(interval).lower(), interval)

        # Yahoo Finance 'end' is exclusive. If start_date >= end_date, adjust end_date forward
        adj_start = start_date
        adj_end = end_date
        if adj_start >= adj_end:
            try:
                adj_end = (pd.to_datetime(adj_start) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                pass

        def _fetch():
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=adj_start, end=adj_end, interval=yf_interval)
            if df is None or df.empty:
                raise YFinanceError(f"No history found for {yf_symbol} ({adj_start} to {adj_end})")
            return df

        raw_df = self._execute_with_retry(_fetch)
        return validate_ohlcv_dataframe(raw_df, symbol=symbol)

    def get_historical(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Alias for get_historical_ohlcv."""
        return self.get_historical_ohlcv(symbol, start_date, end_date, interval)

    def get_quote(self, symbol: str) -> QuoteData:
        """Fetch live quote data."""
        yf_symbol = to_yfinance_symbol(symbol)

        def _fetch():
            ticker = yf.Ticker(yf_symbol)
            fast = getattr(ticker, "fast_info", None)
            if fast and getattr(fast, "last_price", None) is not None:
                ltp = _clean_float(fast.last_price, 0.0)
                prev_close = _clean_float(fast.previous_close, ltp)
                open_p = _clean_float(fast.open, ltp)
                high_p = _clean_float(fast.day_high, ltp)
                low_p = _clean_float(fast.day_low, ltp)
                vol = int(_clean_float(getattr(fast, "last_volume", 0), 0.0))
            else:
                hist = ticker.history(period="2d")
                if hist is None or hist.empty:
                    raise YFinanceError(f"Unable to retrieve quote for {yf_symbol}")
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest
                ltp = _clean_float(latest["Close"], 0.0)
                prev_close = _clean_float(prev["Close"], ltp)
                open_p = _clean_float(latest["Open"], ltp)
                high_p = _clean_float(latest["High"], ltp)
                low_p = _clean_float(latest["Low"], ltp)
                hist_vol = latest.get("Volume", 0) if hasattr(latest, "get") else getattr(latest, "Volume", 0)
                vol = int(_clean_float(hist_vol, 0.0))

            change = ltp - prev_close
            change_pct = (change / prev_close) * 100.0 if prev_close else 0.0

            return QuoteData(
                symbol=symbol.upper(),
                exchange="NSE" if yf_symbol.endswith(".NS") else "GLOBAL",
                ltp=round(ltp, 2),
                open=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(prev_close, 2),
                volume=vol,
                change=round(change, 2),
                change_pct=round(change_pct, 2),
                provider="yfinance",
            )

        return self._execute_with_retry(_fetch)

    def get_fundamentals(self, symbol: str) -> CompanyFundamentals:
        """Fetch comprehensive fundamentals for a company."""
        yf_symbol = to_yfinance_symbol(symbol)

        def _fetch():
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info or {}
            if not info:
                raise YFinanceError(f"No fundamental info found for {yf_symbol}")

            pe_val = info.get("trailingPE")
            pb_val = info.get("priceToBook")
            return CompanyFundamentals(
                symbol=symbol.upper(),
                company_name=info.get("longName") or info.get("shortName") or symbol.upper(),
                sector=info.get("sector"),
                industry=info.get("industry"),
                market_cap=info.get("marketCap"),
                pe_ratio_ttm=pe_val,
                pe_ratio=pe_val,
                forward_pe=info.get("forwardPE"),
                peg_ratio=info.get("pegRatio"),
                price_to_book=pb_val,
                pb_ratio=pb_val,
                eps_ttm=info.get("trailingEps"),
                forward_eps=info.get("forwardEps"),
                dividend_yield=info.get("dividendYield"),
                beta=info.get("beta"),
                fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                fifty_day_average=info.get("fiftyDayAverage"),
                two_hundred_day_average=info.get("twoHundredDayAverage"),
                revenue_ttm=info.get("totalRevenue"),
                gross_profit=info.get("grossProfits"),
                ebitda=info.get("ebitda"),
                net_income=info.get("netIncomeToCommon"),
                profit_margin=info.get("profitMargins"),
                operating_margin=info.get("operatingMargins"),
                return_on_equity=info.get("returnOnEquity"),
                return_on_assets=info.get("returnOnAssets"),
                debt_to_equity=info.get("debtToEquity"),
                current_ratio=info.get("currentRatio"),
                book_value=info.get("bookValue"),
                free_cash_flow=info.get("freeCashflow"),
                provider="yfinance",
            )

        return self._execute_with_retry(_fetch)

    def get_news(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> List[NewsArticle]:
        """Fetch recent news articles for symbol."""
        yf_symbol = to_yfinance_symbol(symbol)

        def _fetch():
            ticker = yf.Ticker(yf_symbol)
            try:
                news_items = ticker.get_news(count=limit * 2) or []
            except TypeError:
                try:
                    news_items = ticker.get_news() or []
                except Exception:
                    news_items = getattr(ticker, "news", []) or []
            except Exception:
                news_items = getattr(ticker, "news", []) or []

            articles: List[NewsArticle] = []

            for item in news_items:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", item)
                if not isinstance(content, dict):
                    content = item
                title = content.get("title", "")
                if not title:
                    continue

                summary = content.get("summary", "")
                provider_info = content.get("provider", {})
                publisher = (provider_info.get("displayName") if isinstance(provider_info, dict) else None) or item.get("publisher", "Unknown")

                url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = (url_obj.get("url") if isinstance(url_obj, dict) else None) or item.get("link", "")

                pub_date = None
                pub_date_str = content.get("pubDate")
                if pub_date_str:
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                elif "providerPublishTime" in content or "providerPublishTime" in item:
                    try:
                        pts = content.get("providerPublishTime") or item.get("providerPublishTime")
                        pub_date = datetime.fromtimestamp(int(pts), tz=timezone.utc)
                    except Exception:
                        pass

                articles.append(NewsArticle(
                    title=title,
                    summary=summary,
                    publisher=publisher,
                    url=link,
                    published_at=pub_date,
                    symbol=symbol.upper(),
                    provider="yfinance",
                ))

                if len(articles) >= limit:
                    break

            return articles

        return self._execute_with_retry(_fetch)
