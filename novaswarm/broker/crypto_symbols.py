"""Crypto symbol mapping and top-coin watchlist.

Maps between three symbol formats used across the system:

    Binance pair:    ``BTCUSDT``   (for quotes and paper execution)
    yfinance ticker: ``BTC-USD``   (for upstream agent analysis)
    Base coin:       ``BTC``       (human-friendly display)

The CRYPTO_TOP_20 list provides a scanner watchlist comparable to NIFTY_50
for equities.
"""

from __future__ import annotations

# ── Known quote currencies (ordered by priority for stripping) ─────────────
_QUOTE_CURRENCIES = ("USDT", "FDUSD", "USDC", "BUSD", "TUSD", "USD", "DAI", "EUR", "TRY", "GBP", "BRL", "BTC", "ETH", "BNB")


def to_binance_pair(symbol: str, quote: str = "USDT") -> str:
    """Ensure a symbol is in Binance pair format (e.g., ``BTCUSDT``).

    Args:
        symbol: Any format — ``BTC``, ``BTCUSDT``, ``BTC-USD``, ``btcusdt``, ``BTC/USDT``.
        quote: Quote currency to append if not already present.

    Returns:
        Uppercase Binance pair like ``BTCUSDT``.
    """
    s = symbol.upper().strip().replace("/", "").replace("_", "")
    if not s:
        return ""

    # Handle yfinance format: BTC-USD → BTC
    if "-" in s:
        s = s.split("-")[0]

    # If already ends with a known quote currency, return as-is
    for qc in _QUOTE_CURRENCIES:
        if s.endswith(qc) and len(s) > len(qc):
            return s

    return s + quote.upper()


def to_yfinance_ticker(symbol: str, quote: str = "USD") -> str:
    """Convert to yfinance crypto format (e.g., ``BTC-USD``).

    Args:
        symbol: Any format — ``BTCUSDT``, ``BTC``, ``BTC-USD``, ``BTC/USDT``.
        quote: Quote currency for yfinance (always USD for crypto).

    Returns:
        yfinance ticker like ``BTC-USD``.
    """
    s = symbol.upper().strip().replace("/", "").replace("_", "")
    if not s:
        return ""

    # Handle existing hyphenated formats (e.g. BTC-USD, BTC-USDT)
    if "-" in s:
        base = s.split("-")[0]
        return f"{base}-{quote.upper()}"

    # Strip known quote currencies
    base = _strip_quote(s)
    if not base:
        base = s
    return f"{base}-{quote.upper()}"


def from_binance_pair(pair: str) -> tuple[str, str]:
    """Split a Binance pair into base and quote currencies.

    Args:
        pair: Binance pair like ``BTCUSDT``, ``BTC/USDT``, or ticker ``BTC-USD``.

    Returns:
        Tuple of ``(base, quote)`` like ``("BTC", "USDT")``.
    """
    s = pair.upper().strip().replace("/", "").replace("_", "")
    if not s:
        return "", ""

    if "-" in s:
        parts = s.split("-", 1)
        return parts[0], parts[1]

    for qc in _QUOTE_CURRENCIES:
        if s.endswith(qc) and len(s) > len(qc):
            base = s[: -len(qc)]
            if base:  # Guard against empty base
                return base, qc

    # Fallback for standalone base coin (e.g. "BTC", "MATIC", "SOL")
    return s, "USDT"


def _strip_quote(s: str) -> str:
    """Strip known quote currency suffix from a symbol."""
    cleaned = s.replace("/", "").replace("_", "")
    for qc in _QUOTE_CURRENCIES:
        if cleaned.endswith(qc) and len(cleaned) > len(qc):
            return cleaned[: -len(qc)]
    return cleaned


# ── Top 20 Crypto Coins by Market Cap ─────────────────────────────────────
# Used as the default crypto watchlist for the scanner.
# All pairs use USDT as quote currency (Binance's most liquid market).

CRYPTO_TOP_20: list[str] = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "MATICUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "AAVEUSDT",
    "FILUSDT",
    "ARBUSDT",
    "OPUSDT",
    "APTUSDT",
]
