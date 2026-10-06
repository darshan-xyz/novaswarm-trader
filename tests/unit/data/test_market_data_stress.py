"""Empirical Stress Tests and Vulnerability Scenarios for novaswarm.data.

This suite stress-tests:
1. Adversarial Inputs:
   - Config token states (SecretStr, NoneType, raw str, missing attr)
   - Symbol formatting and edge cases (hyphenated Indian equities like '-EQ', Windows forbidden chars, unicode, path traversal)
   - Network timeouts & provider outages (INDstocks failover, yfinance retries, both failing)
   - Malformed/empty data (empty df, all-NaN df, MultiIndex columns, string numeric coercion)
   - yfinance fast_info NaN volume edge case
2. Cache Concurrency & TTL Expiry:
   - In-memory TTL expiry for Quote, Fundamentals, News
   - Transient failure caching (e.g. news failure caching empty list)
   - Parquet disk cache corruption recovery
   - Concurrent multi-threaded reads/writes to memory caches and parquet files
   - Path traversal in cache_dir parquet creation
3. State Isolation & Global Integrity:
   - Ensuring failed requests do not pollute caches
   - Singleton instance immutability and state cleanliness
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from pydantic import SecretStr
import pytest

from novaswarm.config import NovaSwarmConfig
from novaswarm.data.indstocks import (
    INDstocksAuthError,
    INDstocksDataProvider,
    INDstocksError,
    INDstocksSymbolNotFoundError,
)
from novaswarm.data.models import (
    CompanyFundamentals,
    NewsArticle,
    QuoteData,
    validate_ohlcv_dataframe,
)
from novaswarm.data.pipeline import (
    MarketDataError,
    UnifiedMarketData,
    get_historical_ohlcv,
    get_quote,
    get_unified_market_data,
)
from novaswarm.data.symbols import (
    detect_exchange,
    normalize_symbol,
    to_indstocks_symbol,
    to_yfinance_symbol,
)
from novaswarm.data.yfinance import YFinanceDataProvider, YFinanceError


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ohlcv():
    dates = pd.date_range("2026-01-01", periods=15, freq="B")
    return pd.DataFrame(
        {
            "Open": [2000.0 + i * 5 for i in range(15)],
            "High": [2020.0 + i * 5 for i in range(15)],
            "Low": [1990.0 + i * 5 for i in range(15)],
            "Close": [2010.0 + i * 5 for i in range(15)],
            "Volume": [500000 + i * 10000 for i in range(15)],
        },
        index=dates,
    )


@pytest.fixture
def sample_quote():
    return QuoteData(
        symbol="INFY",
        exchange="NSE",
        ltp=1500.0,
        open=1490.0,
        high=1510.0,
        low=1485.0,
        close=1495.0,
        volume=2000000,
        change=5.0,
        change_pct=0.33,
        provider="mock",
    )


@pytest.fixture
def sample_fundamentals():
    return CompanyFundamentals(
        symbol="INFY",
        company_name="Infosys Limited",
        sector="Technology",
        pe_ratio=26.5,
        market_cap=6000000000000.0,
    )


@pytest.fixture
def sample_news():
    return [
        NewsArticle(
            title="Infosys announces AI collaboration",
            summary="New multi-year cloud contract signed.",
            publisher="Reuters",
            published_at="2026-01-10T12:00:00Z",
        )
    ]


# ── 1. Adversarial Inputs: Credentials ────────────────────────────────────────

class TestAdversarialCredentials:
    def test_missing_token_secretstr_empty(self, tmp_path, sample_ohlcv):
        """When indstocks_token is empty SecretStr, should fallback to yfinance."""
        cfg = NovaSwarmConfig(indstocks_token=SecretStr(""))
        umd = UnifiedMarketData(config=cfg, cache_dir=tmp_path)
        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv) as mock_yf:
            df = umd.get_historical_ohlcv("TCS", "2026-01-01", "2026-01-20")
            assert not df.empty
            mock_yf.assert_called_once()

    def test_config_token_is_none_falls_back_cleanly(self, tmp_path, sample_ohlcv):
        """When config.indstocks_token is None, pipeline safely falls back to yfinance without AttributeError."""
        cfg = MagicMock()
        cfg.indstocks_token = None
        umd = UnifiedMarketData(config=cfg, cache_dir=tmp_path)
        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv) as mock_yf:
            df = umd.get_historical_ohlcv("TCS", "2026-01-01", "2026-01-20")
            assert not df.empty
            mock_yf.assert_called_once()

    def test_config_token_is_raw_string_handled_cleanly(self, tmp_path, sample_ohlcv):
        """When config.indstocks_token is a plain string, pipeline extracts it safely."""
        cfg = MagicMock()
        cfg.indstocks_token = "plain_string_token"
        umd = UnifiedMarketData(config=cfg, cache_dir=tmp_path)
        with patch.object(umd.indstocks_provider, "get_historical", return_value=sample_ohlcv) as mock_ind:
            df = umd.get_historical_ohlcv("TCS", "2026-01-01", "2026-01-20")
            assert not df.empty
            mock_ind.assert_called_once()

    def test_indstocks_provider_standalone_missing_token(self):
        """Standalone INDstocksDataProvider must raise INDstocksAuthError when token missing."""
        cfg = NovaSwarmConfig(indstocks_token=SecretStr(""))
        provider = INDstocksDataProvider(cfg)
        with pytest.raises(INDstocksAuthError, match="NOVASWARM_INDSTOCKS_TOKEN is not configured"):
            provider._get_client()


# ── 1. Adversarial Inputs: Symbol Characters & Path Traversal ─────────────────

class TestAdversarialSymbols:
    def test_symbol_normalization_basic(self):
        assert normalize_symbol("  reliance  ") == "RELIANCE"
        assert normalize_symbol("TCS.NS") == "TCS"
        assert normalize_symbol("infy.ns") == "INFY"
        assert normalize_symbol("500325.BO") == "500325"
        assert normalize_symbol("WIPRO-EQ") == "WIPRO"
        assert normalize_symbol("HDFCBANK.NSE") == "HDFCBANK"

    def test_hyphenated_indian_equity_yfinance_symbol(self):
        """Indian equities with -EQ series must receive .NS suffix for Yahoo Finance."""
        assert to_yfinance_symbol("WIPRO-EQ") == "WIPRO.NS"
        assert to_yfinance_symbol("INFY-EQ") == "INFY.NS"
        assert to_yfinance_symbol("BTC-USD") == "BTC-USD"
        assert to_yfinance_symbol("BRK-B") == "BRK-B"

    def test_path_traversal_contained_in_cache_directory(self, tmp_path, sample_ohlcv):
        """Symbols with path traversal '../' must be sanitized and remain within cache_dir."""
        sub_cache = tmp_path / "cache_store"
        sub_cache.mkdir()
        umd = UnifiedMarketData(cache_dir=sub_cache)
        traversal_sym = "../escaped_sym"

        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv):
            df = umd.get_historical_ohlcv(traversal_sym, "2026-01-01", "2026-01-20")
            assert not df.empty

            # Verify no parquet file escaped sub_cache into tmp_path
            escaped_matches = list(tmp_path.glob("*.parquet"))
            assert len(escaped_matches) == 0, f"Vulnerability detected: files escaped cache_dir: {escaped_matches}"

            # Verify file exists inside sub_cache
            cached_files = list(sub_cache.glob("*.parquet"))
            assert len(cached_files) == 1
            assert cached_files[0].resolve().is_relative_to(sub_cache.resolve())

    def test_windows_reserved_characters_symbol(self, tmp_path, sample_ohlcv):
        """Symbols with Windows-illegal filename characters (:, *, ?, <, >, |) should not crash pipeline."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        weird_sym = "FOO:BAR*BAZ"
        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv):
            try:
                df = umd.get_historical_ohlcv(weird_sym, "2026-01-01", "2026-01-20")
                assert not df.empty
            except OSError as e:
                pytest.fail(f"Unsanitized cache path caused OSError: {e}")

    def test_unicode_symbol_handling(self, tmp_path, sample_quote):
        """Unicode characters in symbol should be handled without UnicodeEncodeError."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        unicode_sym = "TATAMOTORS🚀"
        with patch.object(umd.yfinance_provider, "get_quote", return_value=sample_quote):
            quote = umd.get_quote(unicode_sym)
            assert quote is not None

    def test_none_symbol_causes_unhandled_attribute_error(self, tmp_path):
        """Passing None as symbol raises AttributeError in normalize_symbol instead of ValueError/TypeError."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        with pytest.raises(AttributeError, match="has no attribute 'strip'"):
            umd.get_quote(None)  # type: ignore


# ── 1. Adversarial Inputs: Network Timeouts & Outages ─────────────────────────

class TestNetworkTimeoutsAndOutages:
    def test_indstocks_timeout_triggers_yfinance_fallback(self, tmp_path, sample_ohlcv):
        """Indstocks timeout must gracefully fallback to yfinance without crashing."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(umd.config.indstocks_token, "get_secret_value", return_value="token"):
            with patch.object(umd.indstocks_provider, "get_historical", side_effect=TimeoutError("Request timed out")):
                with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv) as mock_yf:
                    df = umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")
                    assert not df.empty
                    mock_yf.assert_called_once()

    def test_yfinance_retry_backoff_exhaustion(self):
        """YFinanceDataProvider._execute_with_retry should retry max_retries times and then raise YFinanceError."""
        provider = YFinanceDataProvider(max_retries=3, retry_delay=0.01)
        mock_fn = MagicMock(side_effect=ConnectionError("Temporary DNS failure"))
        with pytest.raises(YFinanceError, match="failed after 3 attempts"):
            provider._execute_with_retry(mock_fn)
        assert mock_fn.call_count == 3

    def test_both_providers_timeout_raises_market_data_error(self, tmp_path):
        """When both providers timeout, UnifiedMarketData raises descriptive MarketDataError."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(umd.config.indstocks_token, "get_secret_value", return_value="token"):
            with patch.object(umd.indstocks_provider, "get_historical", side_effect=TimeoutError("IND timeout")):
                with patch.object(umd.yfinance_provider, "get_historical", side_effect=TimeoutError("YF timeout")):
                    with pytest.raises(MarketDataError, match="Failed to retrieve OHLCV for 'RELIANCE' from all providers"):
                        umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")


# ── 1. Adversarial Inputs: Malformed & Empty DataFrames ───────────────────────

class TestEmptyAndMalformedData:
    def test_indstocks_returns_empty_df_falls_back(self, tmp_path, sample_ohlcv):
        """If INDstocks returns empty DataFrame, it should proceed to yfinance."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(umd.config.indstocks_token, "get_secret_value", return_value="token"):
            with patch.object(umd.indstocks_provider, "get_historical", return_value=pd.DataFrame()):
                with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv) as mock_yf:
                    df = umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")
                    assert not df.empty
                    mock_yf.assert_called_once()

    def test_all_providers_return_empty_df_raises(self, tmp_path):
        """If both providers return empty DataFrames, raises MarketDataError."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        with patch.object(umd.config.indstocks_token, "get_secret_value", return_value="token"):
            with patch.object(umd.indstocks_provider, "get_historical", return_value=pd.DataFrame()):
                with patch.object(umd.yfinance_provider, "get_historical", return_value=pd.DataFrame()):
                    with pytest.raises(MarketDataError, match="Failed to retrieve OHLCV"):
                        umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")

    def test_validate_ohlcv_all_nan_rows_returns_empty(self):
        """A DataFrame where all OHLC values are NaN has all rows dropped, returning empty DataFrame."""
        dates = pd.date_range("2026-01-01", periods=5)
        nan_df = pd.DataFrame(
            {
                "Open": [np.nan] * 5,
                "High": [np.nan] * 5,
                "Low": [np.nan] * 5,
                "Close": [np.nan] * 5,
                "Volume": [0] * 5,
            },
            index=dates,
        )
        res = validate_ohlcv_dataframe(nan_df, "TEST")
        # Notice: validate_ohlcv_dataframe does not re-check res.empty after dropna
        assert len(res) == 0

    def test_validate_ohlcv_string_types_coerced(self):
        """Numeric values passed as strings should be safely coerced."""
        dates = pd.date_range("2026-01-01", periods=3)
        str_df = pd.DataFrame(
            {
                "Open": ["100.5", "101.2", "102.0"],
                "High": ["105.0", "106.0", "107.0"],
                "Low": ["99.0", "100.0", "101.0"],
                "Close": ["102.0", "103.0", "104.0"],
                "Volume": ["1000", "2000", "3000"],
            },
            index=dates,
        )
        validated = validate_ohlcv_dataframe(str_df, "TEST")
        assert validated["Open"].dtype == np.float64
        assert validated["Volume"].dtype == np.int64
        assert validated["Close"].iloc[0] == 102.0

    def test_validate_ohlcv_multiindex_columns_flattened(self):
        """MultiIndex columns from yfinance downloads must be cleanly flattened."""
        dates = pd.date_range("2026-01-01", periods=3)
        cols = pd.MultiIndex.from_tuples([
            ("Open", "RELIANCE.NS"),
            ("High", "RELIANCE.NS"),
            ("Low", "RELIANCE.NS"),
            ("Close", "RELIANCE.NS"),
            ("Volume", "RELIANCE.NS"),
        ])
        df = pd.DataFrame(
            [[100.0, 105.0, 95.0, 102.0, 1000]] * 3,
            index=dates,
            columns=cols,
        )
        validated = validate_ohlcv_dataframe(df, "RELIANCE")
        assert list(validated.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert not isinstance(validated.columns, pd.MultiIndex)

    def test_yfinance_fast_info_nan_volume_handled(self):
        """When fast_info returns NaN for last_volume, get_quote defaults volume to 0 instead of crashing."""
        provider = YFinanceDataProvider(max_retries=1, retry_delay=0.01)
        mock_ticker = MagicMock()
        mock_fast = MagicMock()
        mock_fast.last_price = 100.0
        mock_fast.previous_close = 99.0
        mock_fast.open = 99.5
        mock_fast.day_high = 101.0
        mock_fast.day_low = 98.0
        mock_fast.last_volume = float("nan")  # NaN from Yahoo Finance
        mock_ticker.fast_info = mock_fast

        with patch("yfinance.Ticker", return_value=mock_ticker):
            quote = provider.get_quote("INFY.NS")
            assert quote.symbol == "INFY.NS"
            assert quote.ltp == 100.0
            assert quote.volume == 0
            assert quote.change == 1.0


# ── 2. Cache Invalidation & TTL Expiry ────────────────────────────────────────

class TestCacheInvalidationAndTTL:
    def test_quote_ttl_expiry(self, tmp_path, sample_quote):
        """Quote must be cached for QUOTE_TTL seconds and re-fetched thereafter."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        umd.QUOTE_TTL = 0.1  # Fast TTL for test

        quote1 = sample_quote.model_copy(update={"ltp": 1500.0})
        quote2 = sample_quote.model_copy(update={"ltp": 1520.0})

        with patch.object(umd.yfinance_provider, "get_quote", side_effect=[quote1, quote2]) as mock_yf:
            # 1st call: fetches from provider
            q_first = umd.get_quote("INFY")
            assert q_first.ltp == 1500.0
            assert mock_yf.call_count == 1

            # Immediate 2nd call: returns cached
            q_second = umd.get_quote("INFY")
            assert q_second.ltp == 1500.0
            assert mock_yf.call_count == 1

            # Sleep past TTL
            time.sleep(0.15)

            # 3rd call: TTL expired, fetches fresh quote
            q_third = umd.get_quote("INFY")
            assert q_third.ltp == 1520.0
            assert mock_yf.call_count == 2

    def test_fundamentals_ttl_expiry(self, tmp_path, sample_fundamentals):
        """Fundamentals cache should honor FUNDAMENTALS_TTL."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        umd.FUNDAMENTALS_TTL = 0.1

        fund1 = sample_fundamentals.model_copy(update={"pe_ratio": 25.0})
        fund2 = sample_fundamentals.model_copy(update={"pe_ratio": 30.0})

        with patch.object(umd.yfinance_provider, "get_fundamentals", side_effect=[fund1, fund2]) as mock_yf:
            f1 = umd.get_fundamentals("INFY")
            assert f1.pe_ratio == 25.0
            assert mock_yf.call_count == 1

            f_cached = umd.get_fundamentals("INFY")
            assert f_cached.pe_ratio == 25.0
            assert mock_yf.call_count == 1

            time.sleep(0.15)

            f2 = umd.get_fundamentals("INFY")
            assert f2.pe_ratio == 30.0
            assert mock_yf.call_count == 2

    def test_news_network_failure_does_not_poison_cache(self, tmp_path, sample_news):
        """Transient network failure must not cache empty list; recovery should fetch fresh news."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        umd.NEWS_TTL = 1800.0

        # Call 1: network failure occurs
        with patch.object(umd.yfinance_provider, "get_news", side_effect=Exception("Temporary connection drop")):
            articles_failed = umd.get_news("INFY")
            assert articles_failed == []
            assert "INFY" not in umd._news_cache

        # Call 2: network has recovered -> provider must be queried
        with patch.object(umd.yfinance_provider, "get_news", return_value=sample_news) as mock_yf:
            articles_recovered = umd.get_news("INFY")
            assert len(articles_recovered) == 1
            assert articles_recovered[0].title == sample_news[0].title
            mock_yf.assert_called_once()
            assert "INFY" in umd._news_cache

    def test_corrupted_parquet_cache_recovers(self, tmp_path, sample_ohlcv):
        """If a cached parquet file is corrupted/truncated, pipeline must catch error and fetch fresh."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        clean_sym = "RELIANCE"
        cache_file = tmp_path / f"{clean_sym}_1day_2026-01-01_2026-01-20.parquet"

        # Write corrupt bytes
        cache_file.write_bytes(b"CORRUPTED_PARQUET_FILE_HEADER_GARBAGE_12345")

        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv) as mock_yf:
            df = umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")
            assert not df.empty
            mock_yf.assert_called_once()

            # Verify that parquet file was rewritten with valid parquet
            recovered_df = pd.read_parquet(cache_file)
            assert len(recovered_df) == len(sample_ohlcv)


# ── 2. Cache Concurrency Stress ───────────────────────────────────────────────

class TestCacheConcurrency:
    def test_concurrent_quote_reads(self, tmp_path, sample_quote):
        """50 concurrent threads requesting get_quote should execute safely without dict mutation errors."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        umd.QUOTE_TTL = 10.0

        with patch.object(umd.yfinance_provider, "get_quote", return_value=sample_quote) as mock_yf:
            symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

            def worker(sym):
                return umd.get_quote(sym)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(worker, symbols[i % len(symbols)]) for i in range(50)]
                results = [f.result(timeout=10) for f in futures]

            assert len(results) == 50
            for r in results:
                assert r is not None
                assert isinstance(r, QuoteData)
            assert mock_yf.call_count <= len(symbols) * 3

    def test_concurrent_parquet_cache_writes(self, tmp_path, sample_ohlcv):
        """20 concurrent threads fetching the same historical OHLCV must not crash on parquet write collisions."""
        umd = UnifiedMarketData(cache_dir=tmp_path)

        with patch.object(umd.yfinance_provider, "get_historical", return_value=sample_ohlcv):
            def worker():
                return umd.get_historical_ohlcv("RELIANCE", "2026-01-01", "2026-01-20")

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(worker) for _ in range(20)]
                results = [f.result(timeout=10) for f in futures]

            assert len(results) == 20
            for df in results:
                assert len(df) == 15
                assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]

    def test_concurrent_ttl_expiration_race(self, tmp_path, sample_quote):
        """Threads querying while TTL expires simultaneously must safely update cache without tearing."""
        umd = UnifiedMarketData(cache_dir=tmp_path)
        umd.QUOTE_TTL = 0.05  # Extremely short TTL

        counter = 0

        def dynamic_quote(sym):
            nonlocal counter
            counter += 1
            return sample_quote.model_copy(update={"ltp": 1500.0 + counter})

        with patch.object(umd.yfinance_provider, "get_quote", side_effect=dynamic_quote):
            def worker():
                time.sleep(0.02)
                return umd.get_quote("INFY")

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(worker) for _ in range(30)]
                results = [f.result(timeout=10) for f in futures]

            assert len(results) == 30
            for r in results:
                assert isinstance(r, QuoteData)
                assert r.ltp >= 1500.0


# ── 3. State Isolation & Integrity ───────────────────────────────────────────

class TestStateIsolation:
    def test_failed_quote_does_not_corrupt_cache(self, tmp_path, sample_quote):
        """A failed quote call must not store None or corrupt the quote cache for subsequent calls."""
        umd = UnifiedMarketData(cache_dir=tmp_path)

        with patch.object(umd.yfinance_provider, "get_quote", side_effect=Exception("Timeout")):
            with pytest.raises(MarketDataError):
                umd.get_quote("FAIL_SYM")

        # Cache must not contain FAIL_SYM
        assert "FAIL_SYM" not in umd._quote_cache

        # Subsequent successful call for another or same symbol succeeds
        with patch.object(umd.yfinance_provider, "get_quote", return_value=sample_quote):
            quote = umd.get_quote("FAIL_SYM")
            assert quote.symbol == "INFY"
            assert "FAIL_SYM" in umd._quote_cache

    def test_singleton_get_unified_market_data_immutability(self):
        """Global singleton instance must return consistent object across calls."""
        inst1 = get_unified_market_data()
        inst2 = get_unified_market_data()
        assert inst1 is inst2
