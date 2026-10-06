"""Unit tests for the Unified Market Data Pipeline (skopaq.data).

Tests:
- UnifiedMarketData orchestrator with primary INDstocks and fallback yfinance
- Automatic .NS / .BO symbol normalization
- Mocked quote, historical OHLCV, fundamentals, and news retrieval
- Graceful error handling and provider failover
Zero reliance on live network connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from skopaq.data.models import CompanyFundamentals, NewsArticle, QuoteData, validate_ohlcv_dataframe
from skopaq.data.pipeline import MarketDataError, UnifiedMarketData
from skopaq.data.symbols import normalize_symbol, to_yfinance_symbol


# ── Symbol Normalization Tests ────────────────────────────────────────────────


class TestSymbolResolver:
    def test_normalize_symbol_strips_suffixes(self):
        assert normalize_symbol("RELIANCE.NS") == "RELIANCE"
        assert normalize_symbol("TCS.BO") == "TCS"
        assert normalize_symbol("INFY") == "INFY"
        assert normalize_symbol("reliance.ns") == "RELIANCE"
        assert normalize_symbol("infy-eq") == "INFY"

    def test_to_yfinance_symbol_adds_ns(self):
        assert to_yfinance_symbol("RELIANCE") == "RELIANCE.NS"
        assert to_yfinance_symbol("TCS.NS") == "TCS.NS"
        assert to_yfinance_symbol("INFY.BO") == "INFY.BO"

    def test_to_yfinance_symbol_preserves_crypto_and_indices(self):
        assert to_yfinance_symbol("^NSEI") == "^NSEI"
        assert to_yfinance_symbol("BTC-USD") == "BTC-USD"

    def test_to_yfinance_symbol_indian_equity_series(self):
        """Regression test for Issue 2: Indian equities with -EQ series must receive .NS suffix."""
        assert to_yfinance_symbol("WIPRO-EQ") == "WIPRO.NS"
        assert to_yfinance_symbol("infy-eq") == "INFY.NS"
        assert to_yfinance_symbol("RELIANCE-EQ") == "RELIANCE.NS"
        assert to_yfinance_symbol("TCS.NSE") == "TCS.NS"
        # Verify crypto and global hyphenated tickers are still preserved
        assert to_yfinance_symbol("BTC-USD") == "BTC-USD"
        assert to_yfinance_symbol("BRK-B") == "BRK-B"


# ── Unified Market Data Pipeline Tests ────────────────────────────────────────


@pytest.fixture
def mock_ohlcv_df():
    dates = pd.date_range("2026-02-01", periods=10, freq="B")
    return pd.DataFrame(
        {
            "Open": [2400.0] * 10,
            "High": [2450.0] * 10,
            "Low": [2390.0] * 10,
            "Close": [2420.0] * 10,
            "Volume": [1000000] * 10,
        },
        index=dates,
    )


class TestUnifiedMarketDataOHLCV:
    def test_ohlcv_primary_indstocks_success(self, mock_ohlcv_df, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.indstocks_provider, "get_historical", return_value=mock_ohlcv_df) as mock_ind:
            with patch.object(market_data.yfinance_provider, "get_historical") as mock_yf:
                # Mock token presence so indstocks is attempted
                with patch.object(market_data.config.indstocks_token, "get_secret_value", return_value="valid_token"):
                    df = market_data.get_historical_ohlcv("RELIANCE", "2026-02-01", "2026-02-15")
                    assert not df.empty
                    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
                    mock_ind.assert_called_once()
                    mock_yf.assert_not_called()

    def test_ohlcv_fallback_to_yfinance_on_indstocks_failure(self, mock_ohlcv_df, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.indstocks_provider, "get_historical", side_effect=RuntimeError("Token expired")):
            with patch.object(market_data.yfinance_provider, "get_historical", return_value=mock_ohlcv_df) as mock_yf:
                with patch.object(market_data.config.indstocks_token, "get_secret_value", return_value="valid_token"):
                    df = market_data.get_historical_ohlcv("RELIANCE", "2026-02-01", "2026-02-15")
                    assert not df.empty
                    mock_yf.assert_called_once()
                    args, _ = mock_yf.call_args
                    assert args[0] == "RELIANCE.NS"

    def test_ohlcv_both_fail_raises_market_data_error(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.indstocks_provider, "get_historical", side_effect=Exception("IND down")):
            with patch.object(market_data.yfinance_provider, "get_historical", side_effect=Exception("YF down")):
                with pytest.raises(MarketDataError, match="Failed to retrieve OHLCV"):
                    market_data.get_historical_ohlcv("RELIANCE", "2026-02-01", "2026-02-15")

    def test_ohlcv_invalid_dates_raises_value_error(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with pytest.raises(ValueError, match="start_date must be before"):
            market_data.get_historical_ohlcv("RELIANCE", "2026-03-01", "2026-02-01")

    def test_ohlcv_token_is_none_falls_back_to_yfinance(self, mock_ohlcv_df, tmp_path):
        """Regression test for Issue 1: config.indstocks_token = None must not raise AttributeError."""
        from skopaq.config import SkopaqConfig
        cfg = SkopaqConfig()
        cfg.indstocks_token = None  # type: ignore[assignment]
        market_data = UnifiedMarketData(config=cfg, cache_dir=tmp_path)
        with patch.object(market_data.yfinance_provider, "get_historical", return_value=mock_ohlcv_df) as mock_yf:
            df = market_data.get_historical_ohlcv("RELIANCE", "2026-02-01", "2026-02-15")
            assert not df.empty
            mock_yf.assert_called_once()
            args, _ = mock_yf.call_args
            assert args[0] == "RELIANCE.NS"

    def test_ohlcv_token_is_raw_string_handled(self, mock_ohlcv_df, tmp_path):
        """Regression test for Issue 1: config.indstocks_token as raw str must be handled safely."""
        from skopaq.config import SkopaqConfig
        cfg = SkopaqConfig()
        cfg.indstocks_token = "raw_api_token"  # type: ignore[assignment]
        market_data = UnifiedMarketData(config=cfg, cache_dir=tmp_path)
        with patch.object(market_data.indstocks_provider, "get_historical", return_value=mock_ohlcv_df) as mock_ind:
            df = market_data.get_historical_ohlcv("RELIANCE", "2026-02-01", "2026-02-15")
            assert not df.empty
            mock_ind.assert_called_once()

    def test_ohlcv_cache_path_traversal_sanitized(self, mock_ohlcv_df, tmp_path):
        """Regression test for Issue 5: Path traversal symbols must not write outside cache_dir."""
        sub_cache = tmp_path / "cache_store"
        sub_cache.mkdir()
        market_data = UnifiedMarketData(cache_dir=sub_cache)
        traversal_sym = "../../escaped_sym"

        with patch.object(market_data.yfinance_provider, "get_historical", return_value=mock_ohlcv_df):
            df = market_data.get_historical_ohlcv(traversal_sym, "2026-02-01", "2026-02-15")
            assert not df.empty

            # Assert NO parquet files escaped into parent tmp_path
            escaped_files = list(tmp_path.glob("*.parquet"))
            assert len(escaped_files) == 0, f"Escaped files detected: {escaped_files}"

            # Assert cache file exists safely within sub_cache
            cached_files = list(sub_cache.glob("*.parquet"))
            assert len(cached_files) == 1
            assert cached_files[0].resolve().is_relative_to(sub_cache.resolve())


class TestUnifiedMarketDataQuote:
    def test_quote_primary_success(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        expected = QuoteData(
            symbol="RELIANCE",
            ltp=2500.0,
            open=2480.0,
            high=2510.0,
            low=2475.0,
            close=2490.0,
            volume=1200000,
            change=10.0,
            change_pct=0.4,
        )
        with patch.object(market_data.indstocks_provider, "get_quote", return_value=expected) as mock_ind:
            with patch.object(market_data.config.indstocks_token, "get_secret_value", return_value="valid_token"):
                quote = market_data.get_quote("RELIANCE")
                assert quote.symbol == "RELIANCE"
                assert quote.ltp == 2500.0
                mock_ind.assert_called_once()

    def test_quote_fallback_to_yfinance(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        fallback_quote = QuoteData(
            symbol="RELIANCE",
            ltp=2505.0,
            open=2480.0,
            high=2510.0,
            low=2475.0,
            close=2490.0,
            volume=1200000,
            change=15.0,
            change_pct=0.6,
        )
        with patch.object(market_data.indstocks_provider, "get_quote", side_effect=Exception("Connection reset")):
            with patch.object(market_data.yfinance_provider, "get_quote", return_value=fallback_quote) as mock_yf:
                with patch.object(market_data.config.indstocks_token, "get_secret_value", return_value="valid_token"):
                    quote = market_data.get_quote("RELIANCE")
                    assert quote.ltp == 2505.0
                    mock_yf.assert_called_once()

    def test_quote_both_fail_raises_market_data_error(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.indstocks_provider, "get_quote", side_effect=Exception("IND down")):
            with patch.object(market_data.yfinance_provider, "get_quote", side_effect=Exception("YF down")):
                with pytest.raises(MarketDataError):
                    market_data.get_quote("RELIANCE")

    def test_quote_yfinance_nan_volume_handled(self, tmp_path):
        """Regression test for Issue 3: fast_info with NaN volume must default to 0."""
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        mock_fast = MagicMock()
        mock_fast.last_price = 1500.0
        mock_fast.previous_close = 1490.0
        mock_fast.open = 1495.0
        mock_fast.day_high = 1510.0
        mock_fast.day_low = 1485.0
        mock_fast.last_volume = float("nan")

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_fast

        with patch("yfinance.Ticker", return_value=mock_ticker):
            # Bypass indstocks
            with patch.object(market_data.indstocks_provider, "get_quote", side_effect=Exception("skip")):
                quote = market_data.get_quote("INFY")
                assert quote.symbol == "INFY.NS"
                assert quote.ltp == 1500.0
                assert quote.volume == 0
                assert quote.change == 10.0


class TestUnifiedMarketDataFundamentalsAndNews:
    def test_fundamentals_retrieval(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        expected = CompanyFundamentals(
            symbol="TCS",
            pe_ratio=28.5,
            pb_ratio=11.2,
            market_cap=14000000000000.0,
            sector="Technology",
        )
        with patch.object(market_data.yfinance_provider, "get_fundamentals", return_value=expected):
            fund = market_data.get_fundamentals("TCS")
            assert fund.symbol == "TCS"
            assert fund.pe_ratio == 28.5

    def test_fundamentals_fallback_or_empty_on_missing(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.yfinance_provider, "get_fundamentals", side_effect=Exception("Not found")):
            with pytest.raises(MarketDataError):
                market_data.get_fundamentals("INVALID")

    def test_news_retrieval(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        expected = [
            NewsArticle(
                title="TCS announces Q4 results",
                summary="Strong digital services growth...",
                publisher="Economic Times",
                published_at="2026-03-01T10:00:00Z",
                url="https://economictimes.example.com/tcs-q4",
            )
        ]
        with patch.object(market_data.yfinance_provider, "get_news", return_value=expected):
            news = market_data.get_news("TCS", "2026-03-01")
            assert len(news) == 1
            assert news[0].publisher == "Economic Times"

    def test_news_empty_on_failure(self, tmp_path):
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(market_data.yfinance_provider, "get_news", side_effect=Exception("Network error")):
            news = market_data.get_news("TCS", "2026-03-01")
            assert news == []

    def test_news_network_failure_does_not_poison_cache(self, tmp_path):
        """Regression test for Issue 4: Transient news exception must not cache empty list."""
        market_data = UnifiedMarketData(cache_dir=tmp_path)
        recovered_articles = [
            NewsArticle(
                title="TCS announces Q4 results",
                summary="Strong digital services growth...",
                publisher="Economic Times",
                published_at="2026-03-01T10:00:00Z",
                url="https://economictimes.example.com/tcs-q4",
            )
        ]
        with patch.object(
            market_data.yfinance_provider,
            "get_news",
            side_effect=[Exception("Transient connection drop"), recovered_articles],
        ) as mock_yf:
            # 1st call fails due to transient network drop -> returns []
            res1 = market_data.get_news("TCS", "2026-03-01")
            assert res1 == []
            assert "TCS" not in market_data._news_cache

            # 2nd call: network recovered -> provider is queried again and returns articles
            res2 = market_data.get_news("TCS", "2026-03-01")
            assert len(res2) == 1
            assert res2[0].title == "TCS announces Q4 results"
            assert mock_yf.call_count == 2
            assert "TCS" in market_data._news_cache


class TestValidateOHLCVDataFrame:
    def test_valid_dataframe(self, mock_ohlcv_df):
        validated = validate_ohlcv_dataframe(mock_ohlcv_df, "RELIANCE")
        assert len(validated) == 10
        assert validated.index.name == "Date"
        assert list(validated.columns) == ["Open", "High", "Low", "Close", "Volume"]

    def test_missing_column_raises(self):
        df = pd.DataFrame({"Open": [1.0], "Close": [2.0]}, index=pd.date_range("2026-01-01", periods=1))
        with pytest.raises(ValueError, match="missing required columns"):
            validate_ohlcv_dataframe(df)

    def test_timezone_stripped(self):
        dates = pd.date_range("2026-01-01", periods=3, tz="Asia/Kolkata")
        df = pd.DataFrame(
            {"Open": [1.0, 2.0, 3.0], "High": [2.0, 3.0, 4.0], "Low": [0.5, 1.5, 2.5], "Close": [1.5, 2.5, 3.5], "Volume": [100, 200, 300]},
            index=dates,
        )
        validated = validate_ohlcv_dataframe(df)
        assert validated.index.tz is None

    def test_sorts_chronologically(self):
        dates = pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-02"])
        df = pd.DataFrame(
            {"Open": [1.0, 2.0, 3.0], "High": [2.0, 3.0, 4.0], "Low": [0.5, 1.5, 2.5], "Close": [1.5, 2.5, 3.5], "Volume": [100, 200, 300]},
            index=dates,
        )
        validated = validate_ohlcv_dataframe(df)
        assert list(validated.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02", "2026-01-03"]
