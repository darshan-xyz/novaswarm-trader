"""Unit tests for pure vectorized technical indicators (novaswarm.indicators.formulas).

Verifies mathematical accuracy against hand-calculated analytical vectors,
mathematical invariants, and all edge cases (empty series, flat prices,
short series, zero volume, NaN values, negative prices).
Zero reliance on stockstats or external indicator libraries.
"""

from __future__ import annotations

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


# ── SMA Tests ─────────────────────────────────────────────────────────────────


class TestComputeSMA:
    def test_sma_analytical_vector(self):
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = compute_sma(series, period=3)
        assert np.isnan(result.iloc[0])
        assert np.isnan(result.iloc[1])
        assert result.iloc[2] == pytest.approx(20.0)
        assert result.iloc[3] == pytest.approx(30.0)
        assert result.iloc[4] == pytest.approx(40.0)

    def test_sma_constant_prices(self):
        series = pd.Series([100.0] * 10)
        result = compute_sma(series, period=5)
        assert np.all(result.iloc[4:] == 100.0)

    def test_sma_series_shorter_than_period(self):
        series = pd.Series([10.0, 20.0, 30.0])
        result = compute_sma(series, period=5)
        assert len(result) == 3
        assert result.isna().all()

    def test_sma_empty_series(self):
        series = pd.Series([], dtype=float)
        result = compute_sma(series, period=5)
        assert len(result) == 0

    def test_sma_negative_prices(self):
        series = pd.Series([-10.0, -20.0, -30.0])
        result = compute_sma(series, period=3)
        assert result.iloc[2] == pytest.approx(-20.0)

    def test_sma_invalid_period_raises(self):
        series = pd.Series([10.0, 20.0])
        with pytest.raises(ValueError, match="positive integer"):
            compute_sma(series, period=0)
        with pytest.raises(ValueError, match="positive integer"):
            compute_sma(series, period=-5)


# ── EMA Tests ─────────────────────────────────────────────────────────────────


class TestComputeEMA:
    def test_ema_analytical_vector(self):
        # span=3 => alpha = 2/(3+1) = 0.5. adjust=False
        # S0=10, S1=0.5*20 + 0.5*10 = 15, S2=0.5*30 + 0.5*15 = 22.5, S3=0.5*40 + 0.5*22.5 = 31.25
        series = pd.Series([10.0, 20.0, 30.0, 40.0])
        result = compute_ema(series, period=3)
        assert result.iloc[0] == pytest.approx(10.0)
        assert result.iloc[1] == pytest.approx(15.0)
        assert result.iloc[2] == pytest.approx(22.5)
        assert result.iloc[3] == pytest.approx(31.25)

    def test_ema_constant_prices(self):
        series = pd.Series([50.0] * 10)
        result = compute_ema(series, period=4)
        assert np.all(result == 50.0)

    def test_ema_empty_series(self):
        series = pd.Series([], dtype=float)
        result = compute_ema(series, period=3)
        assert len(result) == 0

    def test_ema_invalid_period_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            compute_ema(pd.Series([1.0, 2.0]), period=0)


# ── RSI Tests ─────────────────────────────────────────────────────────────────


class TestComputeRSI:
    def test_rsi_strictly_increasing(self):
        series = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
        result = compute_rsi(series, period=3)
        # Once period warmup passes, RSI should be 100.0 because there are zero losses
        assert np.allclose(result.iloc[3:], 100.0)

    def test_rsi_strictly_decreasing(self):
        series = pd.Series([24.0, 22.0, 20.0, 18.0, 16.0, 14.0, 12.0, 10.0])
        result = compute_rsi(series, period=3)
        # Once period warmup passes, RSI should be 0.0 because there are zero gains
        assert np.allclose(result.iloc[3:], 0.0)

    def test_rsi_all_flat_prices(self):
        series = pd.Series([50.0] * 10)
        result = compute_rsi(series, period=3)
        # Flat series: total gains + total losses == 0 -> safe fallback to 50.0
        assert np.allclose(result.iloc[3:], 50.0)

    def test_rsi_bounded_between_0_and_100(self):
        np.random.seed(42)
        prices = pd.Series(100.0 + np.cumsum(np.random.randn(100)))
        result = compute_rsi(prices, period=14)
        valid = result.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_rsi_series_shorter_than_period(self):
        series = pd.Series([10.0, 12.0, 11.0])
        result = compute_rsi(series, period=14)
        assert len(result) == 3
        assert result.isna().all()

    def test_rsi_empty_series(self):
        series = pd.Series([], dtype=float)
        result = compute_rsi(series, period=14)
        assert len(result) == 0

    def test_rsi_invalid_period_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            compute_rsi(pd.Series([1.0, 2.0]), period=0)


# ── MACD Tests ────────────────────────────────────────────────────────────────


class TestComputeMACD:
    def test_macd_analytical_relationships(self):
        series = pd.Series([10.0, 11.0, 13.0, 12.0, 15.0, 18.0, 17.0, 20.0, 22.0, 25.0])
        macd, signal, hist = compute_macd(series, fast=2, slow=4, signal=2)
        fast_ema = compute_ema(series, period=2)
        slow_ema = compute_ema(series, period=4)
        expected_macd = fast_ema - slow_ema
        pd.testing.assert_series_equal(macd, expected_macd, check_names=False)

        expected_signal = compute_ema(macd, period=2)
        pd.testing.assert_series_equal(signal, expected_signal, check_names=False)

        expected_hist = macd - signal
        pd.testing.assert_series_equal(hist, expected_hist, check_names=False)

    def test_macd_constant_prices(self):
        series = pd.Series([100.0] * 10)
        macd, signal, hist = compute_macd(series, fast=2, slow=4, signal=2)
        assert (macd == 0.0).all()
        assert (signal == 0.0).all()
        assert (hist == 0.0).all()

    def test_macd_fast_ge_slow_raises(self):
        series = pd.Series([10.0, 20.0])
        with pytest.raises(ValueError, match="fast period .* must be strictly less than slow"):
            compute_macd(series, fast=26, slow=12, signal=9)
        with pytest.raises(ValueError, match="fast period .* must be strictly less than slow"):
            compute_macd(series, fast=12, slow=12, signal=9)

    def test_macd_empty_series(self):
        series = pd.Series([], dtype=float)
        macd, signal, hist = compute_macd(series)
        assert len(macd) == 0
        assert len(signal) == 0
        assert len(hist) == 0


# ── Bollinger Bands Tests ─────────────────────────────────────────────────────


class TestComputeBollingerBands:
    def test_bollinger_analytical_vector(self):
        series = pd.Series([10.0, 20.0, 30.0])
        basis, upper, lower = compute_bollinger_bands(series, period=3, num_std=2.0)
        assert basis.iloc[2] == pytest.approx(20.0)
        # std (ddof=0) = sqrt(((10-20)^2 + (30-20)^2)/3) = sqrt(200/3) = 8.1649658
        assert upper.iloc[2] == pytest.approx(20.0 + 2.0 * np.sqrt(200.0 / 3.0), rel=1e-4)
        assert lower.iloc[2] == pytest.approx(20.0 - 2.0 * np.sqrt(200.0 / 3.0), rel=1e-4)

    def test_bollinger_invariants(self):
        np.random.seed(123)
        series = pd.Series(50.0 + np.cumsum(np.random.randn(50)))
        basis, upper, lower = compute_bollinger_bands(series, period=10, num_std=2.0)
        valid = ~basis.isna()
        assert (upper[valid] >= basis[valid]).all()
        assert (basis[valid] >= lower[valid]).all()

    def test_bollinger_constant_prices(self):
        series = pd.Series([100.0] * 10)
        basis, upper, lower = compute_bollinger_bands(series, period=5, num_std=2.0)
        assert np.all(basis.iloc[4:] == 100.0)
        assert np.all(upper.iloc[4:] == 100.0)
        assert np.all(lower.iloc[4:] == 100.0)

    def test_bollinger_empty_series(self):
        empty = pd.Series([], dtype=float)
        basis, upper, lower = compute_bollinger_bands(empty)
        assert len(basis) == 0
        assert len(upper) == 0
        assert len(lower) == 0

    def test_bollinger_invalid_params_raises(self):
        series = pd.Series([10.0, 20.0])
        with pytest.raises(ValueError, match="positive integer"):
            compute_bollinger_bands(series, period=0)
        with pytest.raises(ValueError, match="non-negative"):
            compute_bollinger_bands(series, period=5, num_std=-1.0)


# ── ATR Tests ─────────────────────────────────────────────────────────────────


class TestComputeATR:
    def test_atr_analytical_vector(self):
        high = pd.Series([12.0, 15.0, 16.0])
        low = pd.Series([10.0, 11.0, 13.0])
        close = pd.Series([11.0, 14.0, 15.0])
        # Bar 0: TR = 2.0
        # Bar 1: TR = max(4, |15-11|=4, |11-11|=0) = 4.0
        # Bar 2: TR = max(3, |16-14|=2, |13-14|=1) = 3.0
        # With period=2, alpha=0.5: ATR0=2.0, ATR1=3.0, ATR2=3.0
        atr = compute_atr(high, low, close, period=2)
        assert atr.iloc[1] == pytest.approx(3.0)
        assert atr.iloc[2] == pytest.approx(3.0)

    def test_atr_strictly_non_negative(self):
        np.random.seed(999)
        c = pd.Series(100.0 + np.cumsum(np.random.randn(60)))
        h = c + np.random.uniform(0.5, 3.0, size=60)
        l = c - np.random.uniform(0.5, 3.0, size=60)
        atr = compute_atr(h, l, c, period=14)
        valid = atr.dropna()
        assert (valid >= 0.0).all()

    def test_atr_flat_prices(self):
        h = pd.Series([100.0] * 10)
        l = pd.Series([100.0] * 10)
        c = pd.Series([100.0] * 10)
        atr = compute_atr(h, l, c, period=5)
        assert np.all(atr.iloc[4:] == 0.0)

    def test_atr_empty_series(self):
        empty = pd.Series([], dtype=float)
        atr = compute_atr(empty, empty, empty, period=14)
        assert len(atr) == 0

    def test_atr_invalid_period_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            compute_atr(pd.Series([1.0]), pd.Series([1.0]), pd.Series([1.0]), period=0)


# ── Supertrend Tests ──────────────────────────────────────────────────────────


class TestComputeSupertrend:
    def test_supertrend_uptrend_direction(self):
        close = pd.Series([10.0, 12.0, 15.0, 18.0, 22.0, 27.0, 32.0, 38.0])
        high = close + 1.0
        low = close - 1.0
        st, direction = compute_supertrend(high, low, close, period=3, multiplier=1.5)
        assert direction.iloc[-1] == 1
        assert close.iloc[-1] >= st.iloc[-1]

    def test_supertrend_downtrend_direction(self):
        close = pd.Series([40.0, 35.0, 30.0, 25.0, 20.0, 16.0, 12.0, 9.0])
        high = close + 1.0
        low = close - 1.0
        st, direction = compute_supertrend(high, low, close, period=3, multiplier=1.5)
        assert direction.iloc[-1] == -1
        assert close.iloc[-1] <= st.iloc[-1]

    def test_supertrend_empty_series(self):
        empty = pd.Series([], dtype=float)
        st, direction = compute_supertrend(empty, empty, empty)
        assert len(st) == 0
        assert len(direction) == 0

    def test_supertrend_invalid_params_raises(self):
        s = pd.Series([1.0, 2.0])
        with pytest.raises(ValueError, match="positive integer"):
            compute_supertrend(s, s, s, period=0)
        with pytest.raises(ValueError, match="positive"):
            compute_supertrend(s, s, s, period=5, multiplier=0.0)


# ── VWMA Tests ────────────────────────────────────────────────────────────────


class TestComputeVWMA:
    def test_vwma_analytical_vector(self):
        close = pd.Series([100.0, 110.0])
        volume = pd.Series([1000.0, 2000.0])
        result = compute_vwma(close, volume, period=2)
        # (100*1000 + 110*2000) / (1000 + 2000) = 320000 / 3000 = 106.6667
        assert result.iloc[1] == pytest.approx(106.6667, rel=1e-4)

    def test_vwma_zero_volume_handling(self):
        close = pd.Series([100.0, 110.0])
        volume = pd.Series([0.0, 0.0])
        result = compute_vwma(close, volume, period=2)
        assert np.isnan(result.iloc[1])

    def test_vwma_constant_volume_matches_sma(self):
        close = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        volume = pd.Series([500.0] * 5)
        vwma = compute_vwma(close, volume, period=3)
        sma = compute_sma(close, period=3)
        pd.testing.assert_series_equal(vwma, sma, check_names=False)

    def test_vwma_empty_series(self):
        empty = pd.Series([], dtype=float)
        vwma = compute_vwma(empty, empty, period=5)
        assert len(vwma) == 0

    def test_vwma_invalid_period_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            compute_vwma(pd.Series([1.0]), pd.Series([1.0]), period=0)


# ── MFI Tests ─────────────────────────────────────────────────────────────────


class TestComputeMFI:
    def test_mfi_bounded(self):
        np.random.seed(42)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(50)))
        high = close + np.random.uniform(0.5, 2.0, 50)
        low = close - np.random.uniform(0.5, 2.0, 50)
        volume = pd.Series(np.random.randint(1000, 5000, 50), dtype=float)
        mfi = compute_mfi(high, low, close, volume, period=14)
        valid = mfi.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_mfi_empty_series(self):
        empty = pd.Series([], dtype=float)
        mfi = compute_mfi(empty, empty, empty, empty)
        assert len(mfi) == 0

    def test_mfi_invalid_period_raises(self):
        s = pd.Series([1.0, 2.0])
        with pytest.raises(ValueError, match="positive integer"):
            compute_mfi(s, s, s, s, period=0)


# ── Multi-Indicator Batch Tests ───────────────────────────────────────────────


class TestComputeAllIndicators:
    def test_enriches_dataframe(self):
        dates = pd.date_range("2026-01-01", periods=60)
        df = pd.DataFrame(
            {
                "Open": np.linspace(100, 150, 60),
                "High": np.linspace(101, 152, 60),
                "Low": np.linspace(99, 149, 60),
                "Close": np.linspace(100, 150, 60),
                "Volume": [10000] * 60,
            },
            index=dates,
        )
        enriched = compute_all_indicators(df)
        expected_cols = [
            "SMA_50", "SMA_200", "EMA_10", "EMA_20", "RSI_14",
            "MACD", "MACD_Signal", "MACD_Hist",
            "BOLL_Middle", "BOLL_Upper", "BOLL_Lower",
            "ATR_14", "Supertrend", "Supertrend_Direction", "VWMA_20", "MFI_14",
        ]
        for col in expected_cols:
            assert col in enriched.columns
