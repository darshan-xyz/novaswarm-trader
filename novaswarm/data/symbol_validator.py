"""Multi-strategy symbol validation for Indian Equities and Cryptocurrencies.

Rejects invalid, hallucinated, or mistyped stock symbols before analysis or trading.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, ConfigDict
import yfinance as yf

from novaswarm.broker.crypto_symbols import (
    CRYPTO_TOP_20,
    to_binance_pair,
    to_yfinance_ticker,
)
from novaswarm.data.symbols import detect_exchange, normalize_symbol, to_yfinance_symbol
from novaswarm.scanner.watchlist import NIFTY_50

logger = logging.getLogger(__name__)

# Cache structure: key -> (timestamp, SymbolValidationResult)
_VALIDATION_CACHE: Dict[str, Tuple[float, SymbolValidationResult]] = {}
_CACHE_TTL = 300.0  # 5 minutes

# Symbol format regex: 1-20 uppercase alphanumeric chars, hyphen, or ampersand
_SYMBOL_REGEX = re.compile(r"^[A-Z0-9&-]{1,20}$")


class SymbolValidationResult(BaseModel):
    """Result of symbol validation check."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    symbol: str
    exchange: str
    company_name: Optional[str] = None
    source: str  # "nifty50", "instruments", "yfinance", "crypto_top20", "crypto_probe", "invalid"
    error: Optional[str] = None


def clear_validation_cache() -> None:
    """Clear in-memory validation cache (useful for testing)."""
    _VALIDATION_CACHE.clear()


def _check_instruments_cache(norm_sym: str) -> Optional[Tuple[str, str]]:
    """Check if symbol exists in INDstocks instruments cache if already downloaded."""
    try:
        from novaswarm.broker.scrip_resolver import _cache
        if not _cache:
            return None
        for exch in ("NSE", "BSE"):
            key = f"{exch}:{norm_sym}"
            if key in _cache:
                return exch, _cache[key]
    except Exception:
        pass
    return None


def _probe_yfinance_sync(yf_sym: str) -> Tuple[bool, Optional[str]]:
    """Probe yfinance synchronously for symbol existence and last price."""
    try:
        ticker = yf.Ticker(yf_sym)
        # Fast check: fast_info last_price
        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            try:
                price = getattr(fast, "last_price", None)
                if price is not None and not (isinstance(price, float) and price != price):
                    if float(price) > 0:
                        return True, None
            except Exception:
                pass

        # Fallback check: 2-day history
        hist = ticker.history(period="2d")
        if hist is not None and not hist.empty:
            return True, None

        return False, f"Symbol '{yf_sym}' has no market trading data on Yahoo Finance."
    except Exception as exc:
        return False, f"Symbol '{yf_sym}' not found: {exc}"


async def validate_symbol(symbol: str, asset_class: str = "equity") -> SymbolValidationResult:
    """Validate a trading symbol across multiple strategies.

    Args:
        symbol: Raw symbol input (e.g. "RELIANCE", "infy", "BTCUSDT", "XYZ123").
        asset_class: "equity" or "crypto".

    Returns:
        SymbolValidationResult indicating validity, normalized symbol, and exchange.
    """
    raw_sym = (symbol or "").strip()
    if not raw_sym:
        return SymbolValidationResult(
            valid=False,
            symbol="",
            exchange="UNKNOWN",
            source="invalid",
            error="Symbol cannot be empty.",
        )

    norm_sym = normalize_symbol(raw_sym)
    cache_key = f"{asset_class.lower()}:{norm_sym}"

    now = time.time()
    if cache_key in _VALIDATION_CACHE:
        ts, cached_res = _VALIDATION_CACHE[cache_key]
        if (now - ts) < _CACHE_TTL:
            return cached_res

    # 1. Regex Guard
    if not _SYMBOL_REGEX.match(norm_sym):
        res = SymbolValidationResult(
            valid=False,
            symbol=norm_sym,
            exchange="UNKNOWN",
            source="invalid",
            error=(
                f"Invalid symbol format '{norm_sym}'. "
                "Symbols must be 1-20 alphanumeric characters (hyphens and & allowed)."
            ),
        )
        _VALIDATION_CACHE[cache_key] = (now, res)
        return res

    # 2. Crypto Asset Class Validation
    if asset_class.lower() == "crypto":
        binance_pair = to_binance_pair(norm_sym)
        # Check Top 20 Watchlist
        if binance_pair in CRYPTO_TOP_20:
            res = SymbolValidationResult(
                valid=True,
                symbol=binance_pair,
                exchange="BINANCE",
                source="crypto_top20",
            )
            _VALIDATION_CACHE[cache_key] = (now, res)
            return res

        # Probe crypto via yfinance
        yf_ticker = to_yfinance_ticker(norm_sym)
        is_valid, err_msg = await asyncio.to_thread(_probe_yfinance_sync, yf_ticker)
        if is_valid:
            res = SymbolValidationResult(
                valid=True,
                symbol=binance_pair,
                exchange="BINANCE",
                source="crypto_probe",
            )
        else:
            res = SymbolValidationResult(
                valid=False,
                symbol=norm_sym,
                exchange="BINANCE",
                source="invalid",
                error=err_msg or f"Crypto symbol '{norm_sym}' could not be verified.",
            )
        _VALIDATION_CACHE[cache_key] = (now, res)
        return res

    # 3. Equity Asset Class Validation
    # Strategy A: NIFTY 50 (Instant 0ms check)
    if norm_sym in NIFTY_50:
        res = SymbolValidationResult(
            valid=True,
            symbol=norm_sym,
            exchange="NSE",
            source="nifty50",
        )
        _VALIDATION_CACHE[cache_key] = (now, res)
        return res

    # Strategy B: Scrip resolver cache if populated
    instr = _check_instruments_cache(norm_sym)
    if instr is not None:
        exch, scrip = instr
        res = SymbolValidationResult(
            valid=True,
            symbol=norm_sym,
            exchange=exch,
            source="instruments",
        )
        _VALIDATION_CACHE[cache_key] = (now, res)
        return res

    # Strategy C: yfinance probe (NSE first, then BSE if detected)
    detected_exch = detect_exchange(raw_sym)
    yf_sym = to_yfinance_symbol(norm_sym, default_exchange=detected_exch)

    is_valid, err_msg = await asyncio.to_thread(_probe_yfinance_sync, yf_sym)
    if is_valid:
        res = SymbolValidationResult(
            valid=True,
            symbol=norm_sym,
            exchange=detected_exch,
            source="yfinance",
        )
    else:
        # If NSE probe failed, try BSE suffix if not already tried
        if detected_exch == "NSE" and not norm_sym.endswith(".BO"):
            bse_sym = f"{norm_sym}.BO"
            bse_valid, _ = await asyncio.to_thread(_probe_yfinance_sync, bse_sym)
            if bse_valid:
                res = SymbolValidationResult(
                    valid=True,
                    symbol=norm_sym,
                    exchange="BSE",
                    source="yfinance",
                )
                _VALIDATION_CACHE[cache_key] = (now, res)
                return res

        res = SymbolValidationResult(
            valid=False,
            symbol=norm_sym,
            exchange=detected_exch,
            source="invalid",
            error=f"Stock symbol '{norm_sym}' not found on NSE/BSE. Please verify the ticker symbol.",
        )

    _VALIDATION_CACHE[cache_key] = (now, res)
    return res
