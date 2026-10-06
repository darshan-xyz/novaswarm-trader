"""Empirical stress-test suite for novaswarm/indicators/formulas.py and novaswarm/indicators/engine.py.

Stress dimensions covered:
1. Extreme prices (e.g. 1e-8, 1e8, 1e-12, 1e12, extreme swings).
2. Zero and negative volume (identically 0, intermittent, negative volume handling).
3. 100% constant series (zero variance flatlines).
4. Negative numbers (negative price series like commodities / futures).
5. All-NaN and interspersed NaN series.
6. Lookback windows exceeding bar counts (0 bars, 1 bar, huge lookbacks).
7. Execution performance benchmark (< 50ms across 10,000 bars for all formulas).
8. Adversarial engine queries, duplicate timestamps, and numeric stability.
"""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
import pytest

from novaswarm.indicators.formulas import (
    compute_all_indicators,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_mfi,
    compute_rsi,
    compute_sma,
    compute_supertrend,
    compute_vwma,
)
from novaswarm.indicators.engine import (
    calculate_indicator_series,
    get_indicators,
)


class TestExtremePrices:
    """Stress tests with extremely small and extremely large price values."""

    def test_sub_penny_extreme_low_prices(self):
        """Verify numeric stability with micro-penny prices (1e-8)."""
        n = 100
        base = pd.Series(np.full(n, 1e-8))
        df = pd.DataFrame({
            "Open": base,
            "High": base * 1.05,
            "Low": base * 0.95,
            "Close": base,
            "Volume": pd.Series(np.full(n, 1000.0)),
        })

        res = compute_all_indicators(df)
        assert res.shape == (n, 21)

        # Check absence of infinite values
        for col in res.columns:
            assert not np.isinf(res[col]).any(), f"Infinite value found in {col}"

        # Indicators like ATR and SMA should scale proportionally without underflow to 0
        atr = res["ATR_14"].dropna()
        assert (atr > 0).all()
        assert (atr < 1e-7).all()

        sma = res["SMA_50"].dropna()
        np.testing.assert_allclose(sma.values, 1e-8, rtol=1e-5)

    def test_giant_extreme_high_prices(self):
        """Verify absence of overflow with giant price values (1e8)."""
        n = 100
        base = pd.Series(np.full(n, 1e8))
        df = pd.DataFrame({
            "Open": base,
            "High": base * 1.05,
            "Low": base * 0.95,
            "Close": base,
            "Volume": pd.Series(np.full(n, 1e9)),
        })

        res = compute_all_indicators(df)
        assert res.shape == (n, 21)

        for col in res.columns:
            assert not np.isinf(res[col]).any(), f"Infinite value found in {col}"

        atr = res["ATR_14"].dropna()
        assert (atr > 1e6).all()

        boll_mid = res["BOLL_Middle"].dropna()
        np.testing.assert_allclose(boll_mid.values, 1e8, rtol=1e-5)

    def test_extreme_price_swings(self):
        """Verify numeric stability under alternating extreme orders of magnitude."""
        n = 60
        # Alternate between 1e-6 and 1e6
        swings = np.array([1e-6 if i % 2 == 0 else 1e6 for i in range(n)])
        close = pd.Series(swings)
        high = close * 1.1
        low = close * 0.9
        vol = pd.Series(np.full(n, 1000.0))

        df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})
        res = compute_all_indicators(df)

        assert not np.isinf(res["RSI_14"].dropna()).any()
        assert not np.isinf(res["MACD"].dropna()).any()
        assert not np.isinf(res["ATR_14"].dropna()).any()
        assert not np.isinf(res["Supertrend"].dropna()).any()


class TestZeroAndNegativeVolume:
    """Stress tests with zero, intermittent, or negative volume."""

    def test_all_zero_volume_indicators(self):
        """Verify VWMA returns NaN and MFI defaults to neutral 50.0 on zero volume."""
        n = 50
        df = pd.DataFrame({
            "Open": pd.Series(np.linspace(100, 150, n)),
            "High": pd.Series(np.linspace(102, 152, n)),
            "Low": pd.Series(np.linspace(98, 148, n)),
            "Close": pd.Series(np.linspace(100, 150, n)),
            "Volume": pd.Series(np.zeros(n)),
        })

        res = compute_all_indicators(df)

        # VWMA should be completely NaN because sum(Volume) is 0
        assert res["VWMA_20"].isna().all()

        # MFI should safely evaluate to 50.0 (neutral) after warmup
        mfi_valid = res["MFI_14"].iloc[14:]
        np.testing.assert_allclose(mfi_valid.values, 50.0)

    def test_intermittent_zero_volume(self):
        """Verify handling of trading days with 0 volume mixed with active volume."""
        n = 50
        vol = np.array([1000.0 if i % 2 == 0 else 0.0 for i in range(n)])
        df = pd.DataFrame({
            "Open": pd.Series(np.linspace(100, 150, n)),
            "High": pd.Series(np.linspace(102, 152, n)),
            "Low": pd.Series(np.linspace(98, 148, n)),
            "Close": pd.Series(np.linspace(100, 150, n)),
            "Volume": pd.Series(vol),
        })

        res = compute_all_indicators(df)
        vwma = res["VWMA_20"].dropna()
        assert len(vwma) > 0
        assert not np.isinf(vwma).any()


class TestConstantSeries:
    """Stress tests on flatline series with zero variance."""

    def test_constant_series_mathematical_invariants(self):
        """Verify indicator behavior when prices never change."""
        n = 60
        df = pd.DataFrame({
            "Open": pd.Series(np.full(n, 250.0)),
            "High": pd.Series(np.full(n, 250.0)),
            "Low": pd.Series(np.full(n, 250.0)),
            "Close": pd.Series(np.full(n, 250.0)),
            "Volume": pd.Series(np.full(n, 5000.0)),
        })

        res = compute_all_indicators(df)

        # SMA & EMA must equal the constant price
        np.testing.assert_allclose(res["SMA_50"].dropna().values, 250.0)
        np.testing.assert_allclose(res["EMA_20"].dropna().values, 250.0)

        # RSI must be exactly 50.0 (neutral, zero gain & loss)
        np.testing.assert_allclose(res["RSI_14"].dropna().values, 50.0)

        # MACD lines and histogram must be 0.0
        np.testing.assert_allclose(res["MACD"].dropna().values, 0.0, atol=1e-8)
        np.testing.assert_allclose(res["MACD_Signal"].dropna().values, 0.0, atol=1e-8)
        np.testing.assert_allclose(res["MACD_Hist"].dropna().values, 0.0, atol=1e-8)

        # Bollinger Bands upper == mid == lower == 250.0
        np.testing.assert_allclose(res["BOLL_Middle"].dropna().values, 250.0)
        np.testing.assert_allclose(res["BOLL_Upper"].dropna().values, 250.0)
        np.testing.assert_allclose(res["BOLL_Lower"].dropna().values, 250.0)

        # ATR must be 0.0
        np.testing.assert_allclose(res["ATR_14"].dropna().values, 0.0)

        # Supertrend must equal price
        np.testing.assert_allclose(res["Supertrend"].dropna().values, 250.0)

        # VWMA must equal 250.0
        np.testing.assert_allclose(res["VWMA_20"].dropna().values, 250.0)

        # MFI must be 50.0
        np.testing.assert_allclose(res["MFI_14"].dropna().values, 50.0)


class TestNegativeNumbers:
    """Stress tests with negative prices (e.g. negative crude oil futures)."""

    def test_negative_prices_indicators(self):
        """Verify formulas execute correctly when price series is negative."""
        n = 60
        close = pd.Series(np.linspace(-40.0, -10.0, n))
        high = close + 2.0
        low = close - 2.0
        vol = pd.Series(np.full(n, 1000.0))

        df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})
        res = compute_all_indicators(df)

        # ATR must ALWAYS be non-negative
        atr = res["ATR_14"].dropna()
        assert (atr >= 0.0).all()
        # High - Low is 4.0, so ATR should converge to 4.0
        np.testing.assert_allclose(atr.values, 4.0, atol=1e-5)

        # RSI must be strictly bounded in [0, 100]
        rsi = res["RSI_14"].dropna()
        assert (rsi >= 0.0).all() and (rsi <= 100.0).all()
        # Strictly rising prices -> RSI should be 100.0
        np.testing.assert_allclose(rsi.values, 100.0)

        # Bollinger Bands: Upper > Middle > Lower
        boll_mid = res["BOLL_Middle"].dropna()
        boll_up = res["BOLL_Upper"].dropna()
        boll_low = res["BOLL_Lower"].dropna()
        assert (boll_up >= boll_mid).all()
        assert (boll_mid >= boll_low).all()


class TestNaNHandling:
    """Stress tests with complete and partial NaN series."""

    def test_all_nan_series_compute_all(self):
        """Verify compute_all_indicators does not crash on an all-NaN DataFrame."""
        n = 50
        df_nan = pd.DataFrame({
            "Open": pd.Series(np.full(n, np.nan)),
            "High": pd.Series(np.full(n, np.nan)),
            "Low": pd.Series(np.full(n, np.nan)),
            "Close": pd.Series(np.full(n, np.nan)),
            "Volume": pd.Series(np.full(n, np.nan)),
        })

        res = compute_all_indicators(df_nan)
        assert res.shape == (n, 21)
        assert res["SMA_50"].isna().all()
        assert res["ATR_14"].isna().all()
        assert res["Supertrend"].isna().all()
        assert res["VWMA_20"].isna().all()

    def test_partial_scattered_nans(self):
        """Verify robustness when NaNs are interspersed in the price series."""
        n = 100
        close = pd.Series(np.linspace(100, 200, n))
        close.iloc[[5, 12, 25, 40, 75]] = np.nan
        high = close + 5.0
        low = close - 5.0
        vol = pd.Series(np.full(n, 1000.0))

        df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol})
        res = compute_all_indicators(df)
        assert res.shape == (n, 21)


class TestHugeLookbackWindows:
    """Stress tests when lookback periods exceed data length or data is minimal."""

    def test_single_bar_dataframe(self):
        """Verify formulas handle single bar DataFrame without IndexError."""
        df_single = pd.DataFrame({
            "Open": [100.0],
            "High": [105.0],
            "Low": [95.0],
            "Close": [102.0],
            "Volume": [1000.0],
        })

        res = compute_all_indicators(df_single)
        assert len(res) == 1
        assert pd.isna(res["SMA_50"].iloc[0])
        assert pd.isna(res["RSI_14"].iloc[0])
        assert pd.isna(res["ATR_14"].iloc[0])
        assert pd.isna(res["Supertrend"].iloc[0])

    def test_bar_count_smaller_than_period(self):
        """Verify lookback windows larger than bar count return NaNs cleanly."""
        n = 10
        c = pd.Series(np.linspace(100, 110, n))
        h = c + 2
        l = c - 2
        v = pd.Series(np.full(n, 100.0))

        assert compute_sma(c, period=50).isna().all()
        assert compute_sma(c, period=200).isna().all()
        assert compute_rsi(c, period=14).isna().all()
        assert compute_atr(h, l, c, period=14).isna().all()
        st, _ = compute_supertrend(h, l, c, period=14)
        assert st.isna().all()
        assert compute_mfi(h, l, c, v, period=14).isna().all()

    def test_empty_dataframe(self):
        """Verify empty DataFrame returns empty DataFrame."""
        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], dtype=float)
        res = compute_all_indicators(empty_df)
        assert len(res) == 0


class TestPerformance10kBars:
    """Performance verification: all formulas must run in < 50ms across 10,000 bars."""

    @pytest.fixture(scope="module")
    def large_ohlcv(self) -> pd.DataFrame:
        np.random.seed(42)
        n = 10000
        dates = pd.date_range("2000-01-01", periods=n, freq="D")
        returns = np.random.normal(0.0005, 0.015, n)
        close_prices = 100.0 * np.exp(np.cumsum(returns))
        high_prices = close_prices * (1.0 + np.abs(np.random.normal(0, 0.005, n)))
        low_prices = close_prices * (1.0 - np.abs(np.random.normal(0, 0.005, n)))
        open_prices = low_prices + np.random.uniform(0, 1, n) * (high_prices - low_prices)
        volume = np.random.lognormal(12, 1, n)

        return pd.DataFrame({
            "Open": open_prices,
            "High": high_prices,
            "Low": low_prices,
            "Close": close_prices,
            "Volume": volume,
        }, index=dates)

    @pytest.mark.parametrize("formula_name,fn", [
        ("compute_sma_50", lambda df: compute_sma(df["Close"], 50)),
        ("compute_sma_200", lambda df: compute_sma(df["Close"], 200)),
        ("compute_ema_10", lambda df: compute_ema(df["Close"], 10)),
        ("compute_ema_20", lambda df: compute_ema(df["Close"], 20)),
        ("compute_rsi_14", lambda df: compute_rsi(df["Close"], 14)),
        ("compute_macd", lambda df: compute_macd(df["Close"], 12, 26, 9)),
        ("compute_bollinger_bands", lambda df: compute_bollinger_bands(df["Close"], 20, 2.0)),
        ("compute_atr_14", lambda df: compute_atr(df["High"], df["Low"], df["Close"], 14)),
        ("compute_supertrend_10", lambda df: compute_supertrend(df["High"], df["Low"], df["Close"], 10, 3.0)),
        ("compute_vwma_20", lambda df: compute_vwma(df["Close"], df["Volume"], 20)),
        ("compute_mfi_14", lambda df: compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"], 14)),
    ])
    def test_individual_formula_latency_under_50ms(self, large_ohlcv, formula_name, fn):
        # Warmup call
        fn(large_ohlcv)

        # Benchmark
        t0 = time.perf_counter()
        fn(large_ohlcv)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert elapsed_ms < 50.0, f"{formula_name} exceeded 50ms latency: took {elapsed_ms:.2f}ms"


class TestEngineStressAndAdversarialQueries:
    """Stress tests on get_indicators and calculate_indicator_series."""

    @pytest.fixture
    def sample_daily_df(self) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        return pd.DataFrame({
            "Open": np.linspace(100, 160, 60),
            "High": np.linspace(105, 165, 60),
            "Low": np.linspace(95, 155, 60),
            "Close": np.linspace(100, 160, 60),
            "Volume": np.full(60, 5000.0),
        }, index=dates)

    def test_get_indicators_huge_lookback_days(self, sample_daily_df):
        """Verify lookback days far exceeding dataset does not crash."""
        res = get_indicators("TEST", "atr,rsi", "2024-02-15", look_back_days=10000, ohlcv_df=sample_daily_df)
        assert "=== atr ===" in res
        assert "=== rsi ===" in res
        assert "ATR =" in res

    def test_get_indicators_zero_and_negative_lookback(self, sample_daily_df):
        """Verify 0 and negative lookback days are clamped safely to 1."""
        res_zero = get_indicators("TEST", "rsi", "2024-02-15", look_back_days=0, ohlcv_df=sample_daily_df)
        res_neg = get_indicators("TEST", "rsi", "2024-02-15", look_back_days=-20, ohlcv_df=sample_daily_df)
        assert "## RSI values" in res_zero
        assert "## RSI values" in res_neg

    def test_get_indicators_duplicate_timestamps(self):
        """Verify robustness when DataFrame has duplicate timestamps."""
        dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04"])
        df = pd.DataFrame({"Open": 100, "High": 102, "Low": 98, "Close": 101, "Volume": 1000}, index=dates)

        res = get_indicators("TEST", "atr", "2024-01-04", look_back_days=5, ohlcv_df=df)
        assert "ATR =" in res
        assert "Error" not in res

    def test_get_indicators_adversarial_queries(self, sample_daily_df):
        """Verify parsing of messy queries with spaces, trailing commas, and mixed case."""
        res = get_indicators(
            "TEST",
            "  RSI_14 ,  MACD , ,  ATR14  , non_existent_ind  ",
            "2024-02-15",
            look_back_days=5,
            ohlcv_df=sample_daily_df,
        )
        assert "=== RSI_14 ===" in res
        assert "=== MACD ===" in res
        assert "=== ATR14 ===" in res
        assert "=== non_existent_ind ===" in res
        assert "Error: Indicator 'non_existent_ind' is not supported" in res

    def test_get_indicators_all_nan_df_formatting(self):
        """Verify all-NaN values format as N/A in text output without crash."""
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df_nan = pd.DataFrame({
            "Open": np.nan,
            "High": np.nan,
            "Low": np.nan,
            "Close": np.nan,
            "Volume": np.nan,
        }, index=dates)

        res = get_indicators("TEST", "rsi,atr,macd", "2024-01-10", look_back_days=5, ohlcv_df=df_nan)
        assert "N/A" in res
        assert "Error" not in res
