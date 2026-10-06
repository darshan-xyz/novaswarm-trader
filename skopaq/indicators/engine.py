"""Technical indicator engine providing formatted output for AI agents and consumers.

Implements native vectorized calculations, strict ascending chronological sorting,
and alias resolution.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from skopaq.indicators.formulas import (
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

logger = logging.getLogger(__name__)

# Canonical metadata and documentation for indicators
INDICATOR_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "close_50_sma": (
        "50 SMA",
        "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
    ),
    "close_200_sma": (
        "200 SMA",
        "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
    ),
    "close_10_ema": (
        "10 EMA",
        "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
    ),
    "macd": (
        "MACD",
        "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
    ),
    "macds": (
        "MACD Signal",
        "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
    ),
    "macdh": (
        "MACD Histogram",
        "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
    ),
    "rsi": (
        "RSI",
        "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
    ),
    "boll": (
        "Bollinger Middle",
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
    ),
    "boll_ub": (
        "Bollinger Upper Band",
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
    ),
    "boll_lb": (
        "Bollinger Lower Band",
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
    ),
    "atr": (
        "ATR",
        "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
    ),
    "vwma": (
        "VWMA",
        "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
    ),
    "supertrend": (
        "Supertrend",
        "Supertrend: Trend-following indicator based on ATR and price volatility. Usage: Stay long when price is above Supertrend, switch to short/cash when price drops below.",
    ),
    "supertrend_direction": (
        "Supertrend Direction",
        "Supertrend Direction: Indicates prevailing trend direction (+1 for Bullish, -1 for Bearish).",
    ),
    "mfi": (
        "MFI",
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals.",
    ),
}

# Static aliases mapping common string queries to canonical names
INDICATOR_ALIASES: dict[str, str] = {
    "sma": "close_50_sma",
    "sma_50": "close_50_sma",
    "sma50": "close_50_sma",
    "50_sma": "close_50_sma",
    "close_50_sma": "close_50_sma",
    "sma_200": "close_200_sma",
    "sma200": "close_200_sma",
    "200_sma": "close_200_sma",
    "close_200_sma": "close_200_sma",
    "ema": "close_10_ema",
    "ema_10": "close_10_ema",
    "ema10": "close_10_ema",
    "10_ema": "close_10_ema",
    "close_10_ema": "close_10_ema",
    "macd": "macd",
    "macd_line": "macd",
    "macds": "macds",
    "macd_signal": "macds",
    "macdh": "macdh",
    "macd_hist": "macdh",
    "macd_histogram": "macdh",
    "rsi": "rsi",
    "rsi_14": "rsi",
    "rsi14": "rsi",
    "boll": "boll",
    "bollinger": "boll",
    "bollinger_middle": "boll",
    "boll_ub": "boll_ub",
    "bollinger_upper": "boll_ub",
    "boll_lb": "boll_lb",
    "bollinger_lower": "boll_lb",
    "atr": "atr",
    "atr_14": "atr",
    "atr14": "atr",
    "vwma": "vwma",
    "vwma_20": "vwma",
    "supertrend": "supertrend",
    "supertrend_direction": "supertrend_direction",
    "mfi": "mfi",
    "mfi_14": "mfi",
}


def _normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure standard capitalized OHLCV column names."""
    df = df.copy()
    col_map = {c.lower(): c for c in df.columns}
    rename_dict = {}
    for target in ["Open", "High", "Low", "Close", "Volume"]:
        if target.lower() in col_map:
            rename_dict[col_map[target.lower()]] = target
    if rename_dict:
        df = df.rename(columns=rename_dict)
    return df


def _fetch_default_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Default OHLCV retrieval trying skopaq.data first, falling back to yfinance."""
    try:
        from skopaq.data.pipeline import get_historical_ohlcv
        df = get_historical_ohlcv(symbol, start_date, end_date)
        if df is not None and not df.empty:
            return _normalize_ohlcv_columns(df)
    except (ImportError, Exception):
        pass

    try:
        import yfinance as yf
        from skopaq.data.symbols import to_yfinance_symbol

        yf_symbol = to_yfinance_symbol(symbol)
        df = yf.download(yf_symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return _normalize_ohlcv_columns(df)
    except Exception as exc:
        logger.debug("yfinance download fallback failed: %s", exc)
    return pd.DataFrame()


def calculate_indicator_series(df: pd.DataFrame, indicator_name: str) -> pd.Series:
    """Compute raw pd.Series for a given indicator query."""
    key = indicator_name.strip().lower()
    canonical = INDICATOR_ALIASES.get(key, key)
    c = df["Close"]
    h = df["High"] if "High" in df.columns else c
    l = df["Low"] if "Low" in df.columns else c
    v = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

    if canonical == "close_50_sma":
        return compute_sma(c, 50)
    if canonical == "close_200_sma":
        return compute_sma(c, 200)
    if canonical == "close_10_ema":
        return compute_ema(c, 10)
    if canonical == "macd":
        return compute_macd(c, 12, 26, 9)[0]
    if canonical == "macds":
        return compute_macd(c, 12, 26, 9)[1]
    if canonical == "macdh":
        return compute_macd(c, 12, 26, 9)[2]
    if canonical == "rsi":
        return compute_rsi(c, 14)
    if canonical == "boll":
        return compute_bollinger_bands(c, 20, 2.0)[0]
    if canonical == "boll_ub":
        return compute_bollinger_bands(c, 20, 2.0)[1]
    if canonical == "boll_lb":
        return compute_bollinger_bands(c, 20, 2.0)[2]
    if canonical == "atr":
        return compute_atr(h, l, c, 14)
    if canonical == "vwma":
        return compute_vwma(c, v, 20)
    if canonical == "supertrend":
        return compute_supertrend(h, l, c, 10, 3.0)[0]
    if canonical == "supertrend_direction":
        return compute_supertrend(h, l, c, 10, 3.0)[1]
    if canonical == "mfi":
        return compute_mfi(h, l, c, v, 14)

    # Dynamic regex fallback for parameterized queries like sma_20, ema_50, 20_sma, close_20_sma
    m_sma = re.match(r"^(?:close_)?(?:sma_?)?(\d+)(?:_?sma)?$", key)
    if m_sma and ("sma" in key or key.isdigit()):
        return compute_sma(c, int(m_sma.group(1)))
    m_ema = re.match(r"^(?:close_)?(?:ema_?)?(\d+)(?:_?ema)?$", key)
    if m_ema and ("ema" in key):
        return compute_ema(c, int(m_ema.group(1)))
    m_rsi = re.match(r"^rsi_?(\d+)$", key)
    if m_rsi:
        return compute_rsi(c, int(m_rsi.group(1)))
    m_atr = re.match(r"^atr_?(\d+)$", key)
    if m_atr:
        return compute_atr(h, l, c, int(m_atr.group(1)))
    m_vwma = re.match(r"^vwma_?(\d+)$", key)
    if m_vwma:
        return compute_vwma(c, v, int(m_vwma.group(1)))

    raise ValueError(
        f"Indicator '{indicator_name}' is not supported. Supported indicators: {list(INDICATOR_DESCRIPTIONS.keys())}"
    )


def _format_single_indicator_output(
    series: pd.Series,
    canonical: str,
    start_date_str: str,
    end_date_str: str,
) -> str:
    """Format an indicator Series into the canonical chronological text report."""
    display_title, description = INDICATOR_DESCRIPTIONS.get(
        canonical, (canonical.upper(), "No description available.")
    )

    # Enforce strict chronological ascending sort and tz-naive DatetimeIndex before slicing
    series = series.sort_index(ascending=True)
    if isinstance(series.index, pd.DatetimeIndex) and series.index.tz is not None:
        series.index = series.index.tz_localize(None)

    # Slice strictly to lookback window
    window_series = series.loc[start_date_str:end_date_str]
    if window_series.empty:
        # Fallback to tail if index dates don't match exact strings
        window_series = series.tail(min(len(series), 30))

    lines = []
    for dt, val in window_series.items():
        if hasattr(dt, "strftime"):
            date_str = dt.strftime("%Y-%m-%d %H:%M") if (hasattr(dt, "hour") and (dt.hour != 0 or dt.minute != 0)) else dt.strftime("%Y-%m-%d")
        else:
            date_str = str(dt)[:16] if len(str(dt)) > 10 else str(dt)[:10]
        if pd.isna(val):
            val_str = "N/A"
        elif canonical == "supertrend_direction":
            val_str = f"{int(val)}"
        else:
            val_str = f"{val:.4f}"

        # ATR line formatting: include explicit "ATR = " label to match Strategy 1 in risk/atr.py
        if canonical == "atr":
            lines.append(f"{date_str}: ATR = {val_str}")
        else:
            lines.append(f"{date_str}: {val_str}")

    body = "\n".join(lines)
    if not body:
        body = "No data available for the specified date range.\n"

    return (
        f"## {display_title.upper()} values from {start_date_str} to {end_date_str}\n\n"
        f"{body}\n\n"
        f"{description}"
    )


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
    ohlcv_df: Optional[pd.DataFrame] = None,
) -> str:
    """Retrieve formatted technical indicators for a symbol over a lookback window.

    Supports single indicators, comma-separated indicator lists, parameter aliases,
    and ascending chronological formatting.

    Args:
        symbol: Stock ticker symbol (e.g. 'RELIANCE', 'TCS.NS').
        indicator: Technical indicator name or comma-separated list (e.g. 'atr', 'rsi,macd').
        curr_date: Current trading date (YYYY-MM-DD).
        look_back_days: Number of calendar days to look back (default 30).
        ohlcv_df: Optional pre-fetched OHLCV DataFrame (if provided, skips network calls).

    Returns:
        Formatted string containing date-value lines sorted chronologically ascending.
    """
    if not indicator or not indicator.strip():
        return "Error: Indicator argument cannot be empty."

    # Parse multi-indicator comma-separated queries
    indicators = [ind.strip() for ind in indicator.split(",") if ind.strip()]

    # Parse date window
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return f"Error: Invalid date format '{curr_date}', expected 'YYYY-MM-DD'."

    look_back_days = max(int(look_back_days), 1)
    before_dt = curr_dt - timedelta(days=look_back_days)
    start_date_str = before_dt.strftime("%Y-%m-%d")
    end_date_str = curr_date

    # Acquire historical data with adequate warmup for 200 SMA / MACD / ATR
    if ohlcv_df is not None:
        df = _normalize_ohlcv_columns(ohlcv_df)
    else:
        warmup_days = max(look_back_days + 300, 365)
        warmup_start = (curr_dt - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
        try:
            df = _fetch_default_ohlcv(symbol, warmup_start, end_date_str)
        except Exception as e:
            logger.error("Failed to fetch historical data for %s: %s", symbol, e)
            return f"Error: Could not retrieve market data for {symbol}: {e}"

    if df is None or df.empty:
        return f"Error: No data available for {symbol} up to {curr_date}."

    # Ensure DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        if "Date" in df.columns:
            df = df.set_index(pd.to_datetime(df["Date"]))
        elif "date" in df.columns:
            df = df.set_index(pd.to_datetime(df["date"]))
        else:
            df.index = pd.to_datetime(df.index)

    df = df.sort_index(ascending=True)
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Process single indicator
    if len(indicators) == 1:
        ind = indicators[0]
        try:
            series = calculate_indicator_series(df, ind)
            canonical = INDICATOR_ALIASES.get(ind.lower(), ind.lower())
            return _format_single_indicator_output(series, canonical, start_date_str, end_date_str)
        except Exception as e:
            logger.warning("Error computing indicator '%s' for %s: %s", ind, symbol, e)
            return f"Error: {e}"

    # Process multiple indicators
    parts = []
    for ind in indicators:
        try:
            series = calculate_indicator_series(df, ind)
            canonical = INDICATOR_ALIASES.get(ind.lower(), ind.lower())
            report = _format_single_indicator_output(series, canonical, start_date_str, end_date_str)
            parts.append(f"=== {ind} ===\n{report}")
        except Exception as e:
            parts.append(f"=== {ind} ===\nError: {e}")

    return "\n\n".join(parts)
