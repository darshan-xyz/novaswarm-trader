"""Unit tests for the indicator formatting engine (novaswarm.indicators.engine).

Verifies get_indicators() behavior:
- Single indicator querying
- Multi-indicator comma-separated querying
- Alias resolution (e.g., 'close_50_sma', 'sma_50', 'boll_ub', 'atr')
- Ascending chronological output ordering (vital for novaswarm.risk.atr regex)
- Date range windowing & warmup
- Error handling
"""

from __future__ import annotations

import re
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from novaswarm.indicators.engine import get_indicators


@pytest.fixture
def sample_ohlcv_df():
    """Generates 100 days of valid OHLCV daily data ending on 2026-03-01."""
    dates = pd.date_range(end="2026-03-01", periods=100, freq="D")
    np.random.seed(42)
    close = 2500.0 + np.cumsum(np.random.randn(100) * 15.0)
    high = close + np.random.uniform(5.0, 20.0, 100)
    low = close - np.random.uniform(5.0, 20.0, 100)
    open_p = low + (high - low) * np.random.uniform(0.2, 0.8, 100)
    volume = np.random.randint(500000, 2000000, 100)

    return pd.DataFrame(
        {
            "Open": open_p,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


class TestGetIndicatorsSingle:
    def test_get_rsi_single(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "rsi", "2026-03-01", look_back_days=10)
            assert "## RSI values" in result
            assert "2026-03-01:" in result

    def test_get_atr_format_matches_regex(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "atr", "2026-03-01", look_back_days=10)
            assert "ATR =" in result
            matches = re.findall(r"(?:ATR|atr)\s*[=:,]\s*([\d.]+)", result)
            assert len(matches) > 0
            latest_atr = float(matches[-1])
            assert latest_atr > 0.0

    def test_get_macd_components(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "macd", "2026-03-01", look_back_days=5)
            assert "## MACD values" in result

    def test_get_bollinger_components(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "boll_ub", "2026-03-01", look_back_days=5)
            assert "BOLLINGER" in result or "UPPER" in result

    def test_get_supertrend_components(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "supertrend", "2026-03-01", look_back_days=5)
            assert "SUPERTREND" in result

    def test_get_vwma_single(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "vwma", "2026-03-01", look_back_days=5)
            assert "VWMA" in result


class TestGetIndicatorsMultiAndAliases:
    def test_comma_separated_indicators(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "rsi,macd", "2026-03-01", look_back_days=5)
            assert "=== rsi ===" in result
            assert "=== macd ===" in result

    @pytest.mark.parametrize("alias", ["close_50_sma", "sma_50", "sma50", "sma"])
    def test_sma_aliases(self, sample_ohlcv_df, alias):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", alias, "2026-03-01", look_back_days=5)
            assert "SMA" in result or "sma" in result.lower()

    @pytest.mark.parametrize(
        "ind_name",
        [
            "rsi", "macd", "macds", "macdh",
            "boll", "boll_ub", "boll_lb", "atr",
            "close_50_sma", "close_200_sma", "close_10_ema", "vwma",
        ],
    )
    def test_all_12_mcp_indicator_names(self, sample_ohlcv_df, ind_name):
        """Verifies every single indicator queried by novaswarm.mcp_server resolves cleanly."""
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", ind_name, "2026-03-01", look_back_days=5)
            assert len(result) > 0
            assert "Error" not in result


class TestChronologicalOrdering:
    def test_dates_are_chronologically_ascending(self, sample_ohlcv_df):
        """CRITICAL REQUIREMENT: Output lines MUST be in ascending chronological order."""
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "rsi", "2026-03-01", look_back_days=15)
            date_matches = re.findall(r"(\d{4}-\d{2}-\d{2}):", result)
            assert len(date_matches) >= 2
            # Verify strictly ascending: dates[i] < dates[i+1]
            for i in range(len(date_matches) - 1):
                assert date_matches[i] < date_matches[i + 1], (
                    f"Date ordering violated: {date_matches[i]} came before {date_matches[i+1]}"
                )

    def test_latest_date_at_bottom_for_atr_parser(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "atr", "2026-03-01", look_back_days=15)
            date_matches = re.findall(r"(\d{4}-\d{2}-\d{2}):", result)
            assert date_matches[-1] == "2026-03-01"


class TestDateWindowingAndWarmup:
    def test_output_sliced_to_lookback_days(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "rsi", "2026-03-01", look_back_days=7)
            date_matches = re.findall(r"(\d{4}-\d{2}-\d{2}):", result)
            # 7 calendar days lookback window [curr - 7, curr] has at most 8 days inclusive
            assert len(date_matches) <= 8

    def test_short_history_graceful_handling(self):
        short_df = pd.DataFrame(
            {"Close": [10.0, 20.0, 30.0], "High": [11.0, 21.0, 31.0], "Low": [9.0, 19.0, 29.0], "Volume": [100, 200, 300]},
            index=pd.date_range("2026-02-26", periods=3),
        )
        result = get_indicators("RELIANCE", "sma", "2026-02-28", look_back_days=5, ohlcv_df=short_df)
        assert "SMA" in result


class TestErrorHandlingAndEdgeCases:
    def test_invalid_indicator_name(self, sample_ohlcv_df):
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=sample_ohlcv_df):
            result = get_indicators("RELIANCE", "nonexistent_indicator", "2026-03-01")
            assert "not supported" in result or "Error" in result

    def test_empty_dataframe_from_provider(self):
        empty_df = pd.DataFrame()
        with patch("novaswarm.data.pipeline.get_historical_ohlcv", return_value=empty_df):
            result = get_indicators("UNKNOWN", "rsi", "2026-03-01")
            assert "No data" in result or "Could not retrieve" in result or "Error" in result

    def test_invalid_date_format(self, sample_ohlcv_df):
        result = get_indicators("RELIANCE", "rsi", "01-03-2026")
        assert "Invalid date format" in result
