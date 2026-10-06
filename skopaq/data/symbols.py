"""Symbol normalization and exchange routing for Indian and Global assets."""

from __future__ import annotations

# Common Indian indices and bare symbols
_KNOWN_NSE_SUFFIXES = (".NS", ".NSE", "-EQ")
_KNOWN_BSE_SUFFIXES = (".BO", ".BSE")
_CRYPTO_PAIRS = ("USDT", "BUSD", "USDC", "BTC", "ETH")


def normalize_symbol(symbol: str) -> str:
    """Normalize a symbol to clean bare uppercase format.

    Examples:
        'reliance.ns' -> 'RELIANCE'
        '  TCS.NS '    -> 'TCS'
        'infy-eq'     -> 'INFY'
        '500325.BO'   -> '500325'
    """
    sym = symbol.strip().upper()
    for sfx in _KNOWN_NSE_SUFFIXES + _KNOWN_BSE_SUFFIXES:
        if sym.endswith(sfx):
            return sym[:-len(sfx)]
    return sym


def detect_exchange(symbol: str) -> str:
    """Detect destination exchange for symbol."""
    sym = symbol.strip().upper()
    if any(sym.endswith(s) for s in _KNOWN_BSE_SUFFIXES) or (sym.isdigit() and len(sym) == 6):
        return "BSE"
    if any(sym.endswith(pair) for pair in _CRYPTO_PAIRS):
        return "BINANCE"
    if sym.startswith("^"):
        return "GLOBAL"
    if "." in sym and not any(sym.endswith(s) for s in _KNOWN_NSE_SUFFIXES):
        return "GLOBAL"
    return "NSE"


def to_indstocks_symbol(symbol: str) -> tuple[str, str]:
    """Format symbol for INDstocks API.

    Returns:
        tuple[bare_symbol, exchange] (e.g. ('RELIANCE', 'NSE'))
    """
    exchange = detect_exchange(symbol)
    bare = normalize_symbol(symbol)
    return bare, exchange if exchange in ("NSE", "BSE") else "NSE"


def to_yfinance_symbol(symbol: str, default_exchange: str = "NSE") -> str:
    """Format symbol for Yahoo Finance API.

    Appends .NS for Indian NSE equities if not already present.
    Leaves US equities (e.g. AAPL, MSFT), indices (^NSEI), and cryptos (BTC-USD) intact.
    """
    sym = symbol.strip().upper()

    # Already has yfinance-compatible suffix or index prefix
    # Preserves crypto pairs (BTC-USD) and share classes (BRK-B) while allowing Indian equity series (-EQ)
    if (
        sym.startswith("^")
        or sym.endswith(".NS")
        or sym.endswith(".BO")
        or ("-" in sym and not any(sym.endswith(sfx) for sfx in _KNOWN_NSE_SUFFIXES))
    ):
        return sym

    exchange = detect_exchange(sym)
    if exchange == "NSE":
        return f"{normalize_symbol(sym)}.NS"
    elif exchange == "BSE":
        return f"{normalize_symbol(sym)}.BO"
    elif exchange == "BINANCE":
        for pair in _CRYPTO_PAIRS:
            if sym.endswith(pair):
                base = sym[:-len(pair)]
                return f"{base}-USD"
        return sym

    # US or global ticker
    return sym
