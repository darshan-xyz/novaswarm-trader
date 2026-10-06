"""Tests for ATR data fetching and parsing.

Validates the fallback estimate, regex-based parser, and integration
with native indicator engine (skopaq.indicators.engine.get_indicators).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from skopaq.indicators.engine import get_indicators
from skopaq.risk.atr import _parse_atr_value, estimate_atr, fetch_atr


# ── Estimate ATR ──────────────────────────────────────────────────────────────


class TestEstimateATR:
    def test_default_2pct(self):
        """Default: 2% of price."""
        assert estimate_atr(2500.0) == 50.0

    def test_custom_pct(self):
        assert estimate_atr(1000.0, pct=0.03) == 30.0

    def test_zero_price(self):
        assert estimate_atr(0) == 0.0

    def test_negative_price(self):
        """Negative price should return positive ATR (abs)."""
        assert estimate_atr(-100.0) == 2.0  # abs(-100 * 0.02)


# ── Parse ATR value ───────────────────────────────────────────────────────────


class TestParseATRValue:
    def test_standard_format(self):
        """'ATR = 45.23' pattern."""
        raw = "2026-03-01: ATR = 45.23"
        assert _parse_atr_value(raw) == 45.23

    def test_csv_format(self):
        """'date,ATR\\n2026-03-01,45.23' pattern."""
        raw = "date,ATR\n2026-02-28,42.10\n2026-03-01,45.23"
        assert _parse_atr_value(raw) == 45.23

    def test_colon_format(self):
        """'ATR: 45.23' pattern."""
        raw = "Latest ATR: 45.23"
        assert _parse_atr_value(raw) == 45.23

    def test_lowercase(self):
        raw = "atr = 33.5"
        assert _parse_atr_value(raw) == 33.5

    def test_multiple_values_takes_last(self):
        """Multiple ATR values → take the most recent (last in text)."""
        raw = "ATR = 40.0\nATR = 42.0\nATR = 45.0"
        assert _parse_atr_value(raw) == 45.0

    def test_fallback_to_numeric_extraction(self):
        """No explicit ATR label → extract number from last lines."""
        raw = "Technical Analysis Report\nVolatility: moderate\n2026-03-01, 45.23"
        result = _parse_atr_value(raw)
        assert result == 45.23

    def test_no_numbers_returns_none(self):
        raw = "No data available for this symbol"
        assert _parse_atr_value(raw) is None

    def test_empty_string_returns_none(self):
        assert _parse_atr_value("") is None

    def test_unreasonable_value_filtered(self):
        """Values outside 0.1–10000 range should be filtered out."""
        raw = "timestamp: 1709251200"  # Unix timestamp, not ATR
        assert _parse_atr_value(raw) is None


# ── Fetch ATR Decoupled to Native Indicator Engine ───────────────────────────


@pytest.fixture
def synthetic_ohlcv():
    dates = pd.date_range(end="2026-03-01", periods=50, freq="B")
    return pd.DataFrame(
        {
            "Open": [2400.0] * 50,
            "High": [2455.0] * 50,
            "Low": [2400.0] * 50,
            "Close": [2450.0] * 50,
            "Volume": [1000000] * 50,
        },
        index=dates,
    )


class TestFetchATR:
    """Test fetch_atr decoupled to native skopaq.indicators.engine."""

    def test_vendor_failure_returns_none(self):
        """When vendor/provider fails, return None."""
        with patch("skopaq.indicators.engine.get_indicators", side_effect=RuntimeError("Data unavailable")):
            result = fetch_atr("RELIANCE", "2026-03-01")
        assert result is None

    def test_vendor_returns_empty(self):
        with patch("skopaq.indicators.engine.get_indicators", return_value=""):
            result = fetch_atr("RELIANCE", "2026-03-01")
        assert result is None

    def test_vendor_returns_valid_data(self):
        with patch("skopaq.indicators.engine.get_indicators", return_value="2026-03-01: ATR = 55.0000"):
            result = fetch_atr("RELIANCE", "2026-03-01")
        assert result == 55.0

    def test_fetch_atr_delegates_to_native_engine(self, synthetic_ohlcv):
        """Verify fetch_atr works seamlessly when routed to native get_indicators."""
        with patch(
            "skopaq.indicators.engine.get_indicators",
            side_effect=lambda sym, ind, date, lb: get_indicators(
                sym, ind, date, lb, ohlcv_df=synthetic_ohlcv
            ),
        ):
            val = fetch_atr("RELIANCE", "2026-03-01")
        assert val is not None
        assert val == pytest.approx(55.0, rel=1e-2)

    def test_parse_atr_value_with_native_engine_output(self, synthetic_ohlcv):
        """Directly verify that native get_indicators output matches _parse_atr_value regex."""
        output = get_indicators("RELIANCE", "atr", "2026-03-01", look_back_days=10, ohlcv_df=synthetic_ohlcv)
        parsed = _parse_atr_value(output)
        assert parsed is not None
        assert parsed == pytest.approx(55.0, rel=1e-2)

