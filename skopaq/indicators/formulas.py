"""Pure vectorized technical indicator formulas using NumPy and Pandas.

Clean-room mathematical implementations of standard technical analysis indicators.
Completely decoupled from third-party indicator libraries.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Compute Simple Moving Average (SMA).

    Args:
        series: Price series (typically Close).
        period: Number of periods for rolling window (default 20).

    Returns:
        pd.Series containing the SMA values.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if len(series) == 0:
        return pd.Series([], dtype=float, index=series.index)
    return series.rolling(window=period, min_periods=period).mean()


def compute_ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Compute Exponential Moving Average (EMA).

    Uses recursive smoothing S_t = alpha * Y_t + (1 - alpha) * S_{t-1}
    with alpha = 2 / (period + 1), implemented via adjust=False.

    Args:
        series: Price series (typically Close).
        period: Number of periods for EMA span (default 20).

    Returns:
        pd.Series containing the EMA values.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if len(series) == 0:
        return pd.Series([], dtype=float, index=series.index)
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index (RSI) using J. Welles Wilder's smoothing.

    Uses Wilder's exponential smoothing factor alpha = 1 / period.
    Edge cases:
      - Monotonically increasing prices: RSI = 100.0
      - Monotonically decreasing prices: RSI = 0.0
      - Flat prices (zero volatility): RSI = 50.0

    Args:
        close: Close price series.
        period: Lookback period (default 14).

    Returns:
        pd.Series containing RSI values in range [0, 100].
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    n = len(close)
    if n == 0:
        return pd.Series([], dtype=float, index=close.index)

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's smoothing: alpha = 1 / period
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    total = avg_gain + avg_loss
    safe_total = np.where(total == 0.0, 1.0, total)
    rsi_arr = np.where(total == 0.0, 50.0, 100.0 * (avg_gain / safe_total))

    res = pd.Series(rsi_arr, index=close.index, dtype=float, name=f"rsi_{period}")
    if n >= period:
        res.iloc[:period] = np.nan
    else:
        res.iloc[:] = np.nan
    return res


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute Moving Average Convergence Divergence (MACD).

    Args:
        close: Close price series.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal line EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram).
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("All MACD periods must be positive integers")
    if fast >= slow:
        raise ValueError(f"fast period ({fast}) must be strictly less than slow period ({slow})")

    if len(close) == 0:
        empty = pd.Series([], dtype=float, index=close.index)
        return empty.copy(), empty.copy(), empty.copy()

    ema_fast = compute_ema(close, period=fast)
    ema_slow = compute_ema(close, period=slow)
    macd_line = ema_fast - ema_slow
    macd_line.name = "macd"

    signal_line = compute_ema(macd_line, period=signal)
    signal_line.name = "macd_signal"

    histogram = macd_line - signal_line
    histogram.name = "macd_hist"

    return macd_line, signal_line, histogram


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute Bollinger Bands.

    Args:
        close: Close price series.
        period: Basis SMA period (default 20).
        num_std: Standard deviation multiplier (default 2.0).

    Returns:
        Tuple of (basis, upper_band, lower_band).
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if num_std < 0.0:
        raise ValueError(f"num_std must be non-negative, got {num_std}")

    if len(close) == 0:
        empty = pd.Series([], dtype=float, index=close.index)
        return empty.copy(), empty.copy(), empty.copy()

    basis = close.rolling(window=period, min_periods=period).mean()
    basis.name = "boll_middle"

    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = basis + (num_std * std)
    upper.name = "boll_upper"

    lower = basis - (num_std * std)
    lower.name = "boll_lower"

    return basis, upper, lower


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Compute Average True Range (ATR) using Wilder's smoothing.

    TR = max(High - Low, |High - PrevClose|, |Low - PrevClose|).
    ATR = EWM(TR, alpha = 1 / period, adjust = False).

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        period: ATR lookback period (default 14).

    Returns:
        pd.Series of non-negative ATR values.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if len(close) == 0:
        return pd.Series([], dtype=float, index=close.index)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr.iloc[0] = tr1.iloc[0]

    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    atr.name = f"atr_{period}"
    return atr


def compute_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:
    """Compute Supertrend indicator with ratchet mechanism.

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        period: ATR period for band width (default 10).
        multiplier: ATR multiplier (default 3.0).

    Returns:
        Tuple of (supertrend_line, supertrend_direction).
        Direction is +1 (Bullish / Uptrend) or -1 (Bearish / Downtrend).
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if multiplier <= 0.0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")

    n = len(close)
    if n == 0:
        empty = pd.Series([], dtype=float, index=close.index)
        return empty.copy(), empty.copy()

    atr = compute_atr(high, low, close, period=period)
    hl2 = (high + low) / 2.0

    basic_upper = (hl2 + multiplier * atr).to_numpy()
    basic_lower = (hl2 - multiplier * atr).to_numpy()
    c = close.to_numpy()

    final_upper = np.zeros(n, dtype=float)
    final_lower = np.zeros(n, dtype=float)
    trend = np.ones(n, dtype=int)
    supertrend = np.full(n, np.nan, dtype=float)

    start_idx = period - 1
    if start_idx >= n:
        return pd.Series(supertrend, index=close.index, name="supertrend"), pd.Series(trend, index=close.index, name="supertrend_direction")

    final_upper[start_idx] = basic_upper[start_idx]
    final_lower[start_idx] = basic_lower[start_idx]
    trend[start_idx] = 1 if c[start_idx] >= basic_lower[start_idx] else -1
    supertrend[start_idx] = final_lower[start_idx] if trend[start_idx] == 1 else final_upper[start_idx]

    for i in range(start_idx + 1, n):
        # Ratchet lower band
        if basic_lower[i] > final_lower[i - 1] or c[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Ratchet upper band
        if basic_upper[i] < final_upper[i - 1] or c[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Determine trend direction
        if trend[i - 1] == 1 and c[i] < final_lower[i]:
            trend[i] = -1
        elif trend[i - 1] == -1 and c[i] > final_upper[i]:
            trend[i] = 1
        else:
            trend[i] = trend[i - 1]

        supertrend[i] = final_lower[i] if trend[i] == 1 else final_upper[i]

    return (
        pd.Series(supertrend, index=close.index, name="supertrend"),
        pd.Series(trend, index=close.index, name="supertrend_direction"),
    )


def compute_vwma(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Compute Volume-Weighted Moving Average (VWMA).

    VWMA = sum(Close * Volume, period) / sum(Volume, period).

    Args:
        close: Close price series.
        volume: Volume series.
        period: Rolling window period (default 20).

    Returns:
        pd.Series of VWMA values. Returns NaN when rolling volume is 0.
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if len(close) == 0:
        return pd.Series([], dtype=float, index=close.index)

    pv = close * volume
    sum_pv = pv.rolling(window=period, min_periods=period).sum()
    sum_v = volume.rolling(window=period, min_periods=period).sum()

    safe_sum_v = sum_v.replace(0.0, np.nan)
    vwma = sum_pv / safe_sum_v
    vwma.name = f"vwma_{period}"
    return vwma


def compute_mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Compute Money Flow Index (MFI).

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        volume: Volume series.
        period: Lookback period (default 14).

    Returns:
        pd.Series of MFI values in range [0, 100].
    """
    if period <= 0:
        raise ValueError(f"period must be a positive integer, got {period}")
    if len(close) == 0:
        return pd.Series([], dtype=float, index=close.index)

    typical_price = (high + low + close) / 3.0
    money_flow = typical_price * volume
    delta = typical_price.diff()

    pos_flow = np.where(delta > 0, money_flow, 0.0)
    neg_flow = np.where(delta < 0, money_flow, 0.0)

    pos_sum = pd.Series(pos_flow, index=close.index).rolling(window=period, min_periods=period).sum()
    neg_sum = pd.Series(neg_flow, index=close.index).rolling(window=period, min_periods=period).sum()

    total_sum = pos_sum + neg_sum
    safe_total = np.where(total_sum == 0.0, 1.0, total_sum)
    mfi = np.where(total_sum == 0.0, 50.0, 100.0 * (pos_sum / safe_total))

    res = pd.Series(mfi, index=close.index, name=f"mfi_{period}")
    res.iloc[:period] = np.nan
    return res


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich an OHLCV DataFrame with all standard technical indicators.

    Args:
        df: DataFrame with 'Open', 'High', 'Low', 'Close', 'Volume' columns.

    Returns:
        New enriched DataFrame containing all computed indicator columns.
    """
    res = df.copy()
    col_map = {str(col).lower(): col for col in res.columns}
    c = res[col_map["close"]] if "close" in col_map else (res["Close"] if "Close" in res.columns else pd.Series(dtype=float))
    h = res[col_map["high"]] if "high" in col_map else (res["High"] if "High" in res.columns else c)
    l = res[col_map["low"]] if "low" in col_map else (res["Low"] if "Low" in res.columns else c)
    v = res[col_map["volume"]] if "volume" in col_map else (res["Volume"] if "Volume" in res.columns else pd.Series(0, index=res.index))

    res["SMA_50"] = compute_sma(c, 50)
    res["SMA_200"] = compute_sma(c, 200)
    res["EMA_10"] = compute_ema(c, 10)
    res["EMA_20"] = compute_ema(c, 20)
    res["RSI_14"] = compute_rsi(c, 14)

    macd, macds, macdh = compute_macd(c, 12, 26, 9)
    res["MACD"] = macd
    res["MACD_Signal"] = macds
    res["MACD_Hist"] = macdh

    mid, up, low = compute_bollinger_bands(c, 20, 2.0)
    res["BOLL_Middle"] = mid
    res["BOLL_Upper"] = up
    res["BOLL_Lower"] = low

    res["ATR_14"] = compute_atr(h, l, c, 14)
    st, st_dir = compute_supertrend(h, l, c, 10, 3.0)
    res["Supertrend"] = st
    res["Supertrend_Direction"] = st_dir

    res["VWMA_20"] = compute_vwma(c, v, 20)
    res["MFI_14"] = compute_mfi(h, l, c, v, 14)

    return res
