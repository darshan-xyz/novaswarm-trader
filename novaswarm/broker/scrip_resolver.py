"""Symbol → scrip-code resolver using INDstocks instruments CSV.

The INDstocks API requires ``scrip-codes=NSE_2885`` format for all market
data endpoints.  This module downloads the instruments master and caches
the mapping in memory for the session.

Usage::

    from novaswarm.broker.scrip_resolver import resolve_scrip_code

    async with INDstocksClient(config, token_mgr) as client:
        scrip = await resolve_scrip_code(client, "RELIANCE")
        # → "NSE_2885"
"""

from __future__ import annotations

import csv
import io
import logging
import time

from novaswarm.broker.client import INDstocksClient

logger = logging.getLogger(__name__)

# In-memory cache: {"NSE:RELIANCE": "NSE_2885", ...}
_cache: dict[str, str] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 3600  # 1 hour


async def resolve_scrip_code(
    client: INDstocksClient,
    symbol: str,
    exchange: str = "NSE",
) -> str:
    """Resolve a human-readable symbol to a scrip-code.

    Downloads the instruments CSV on first call (or after TTL expires),
    parses it, and returns ``{exchange}_{security_id}`` format.

    Args:
        client: An open INDstocksClient instance.
        symbol: Trading symbol like ``RELIANCE``, ``TCS``, ``INFY``.
        exchange: Exchange code (default ``NSE``).

    Returns:
        Scrip code like ``NSE_2885``.

    Raises:
        ValueError: If symbol cannot be resolved.
    """
    global _cache, _cache_ts

    clean_sym = symbol.strip().upper()
    clean_exch = exchange.strip().upper()

    if ":" in clean_sym:
        parts = clean_sym.split(":", 1)
        clean_exch = parts[0].strip().upper()
        clean_sym = parts[1].strip().upper()
    elif clean_sym.startswith("NSE_"):
        clean_exch = "NSE"
        clean_sym = clean_sym[4:]
    elif clean_sym.startswith("BSE_"):
        clean_exch = "BSE"
        clean_sym = clean_sym[4:]

    if clean_sym.endswith(".NS") or clean_sym.endswith(".BO"):
        clean_sym = clean_sym[:-3]

    def _lookup(c: dict[str, str]) -> str | None:
        candidates = [
            f"{clean_exch}:{clean_sym}",
            f"{clean_exch}:{clean_sym}-EQ",
            f"{clean_exch}:{clean_sym}-BE",
        ]
        if clean_sym.endswith("-EQ") or clean_sym.endswith("-BE"):
            candidates.append(f"{clean_exch}:{clean_sym[:-3]}")
        for k in candidates:
            if k in c:
                return c[k]
        # Alternate exchange fallback
        alt_exch = "BSE" if clean_exch == "NSE" else "NSE"
        alt_candidates = [
            f"{alt_exch}:{clean_sym}",
            f"{alt_exch}:{clean_sym}-EQ",
            f"{alt_exch}:{clean_sym}-BE",
        ]
        if clean_sym.endswith("-EQ") or clean_sym.endswith("-BE"):
            alt_candidates.append(f"{alt_exch}:{clean_sym[:-3]}")
        for k in alt_candidates:
            if k in c:
                return c[k]
        return None

    # Check cache first
    cached_val = _lookup(_cache)
    if cached_val is not None:
        return cached_val

    # Only re-download if cache is empty or expired
    if not _cache or (time.time() - _cache_ts) >= _CACHE_TTL:
        logger.info("Downloading instruments CSV for scrip-code resolution...")
        csv_text = await client.get_instruments(source="equity")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_text))
        new_cache: dict[str, str] = {}
        for row in reader:
            norm_row = {k.strip().upper(): v.strip() for k, v in row.items() if k and v}
            exch = norm_row.get("EXCH", "").upper()
            trading_symbol = norm_row.get("TRADING_SYMBOL", "").upper()
            custom_symbol = norm_row.get("CUSTOM_SYMBOL", "").upper()
            security_id = norm_row.get("SECURITY_ID", "")
            if exch and security_id:
                if trading_symbol:
                    new_cache[f"{exch}:{trading_symbol}"] = f"{exch}_{security_id}"
                    if trading_symbol.endswith("-EQ") or trading_symbol.endswith("-BE"):
                        base_sym = trading_symbol[:-3]
                        new_cache.setdefault(f"{exch}:{base_sym}", f"{exch}_{security_id}")
                if custom_symbol:
                    new_cache.setdefault(f"{exch}:{custom_symbol}", f"{exch}_{security_id}")
                    if custom_symbol.endswith("-EQ") or custom_symbol.endswith("-BE"):
                        base_sym = custom_symbol[:-3]
                        new_cache.setdefault(f"{exch}:{base_sym}", f"{exch}_{security_id}")

        if new_cache:
            _cache = new_cache
            _cache_ts = time.time()
            logger.info("Instruments cache loaded: %d symbols", len(_cache))
        else:
            logger.warning("Instruments CSV parse yielded 0 symbols")

        resolved = _lookup(_cache)
        if resolved is not None:
            return resolved

    raise ValueError(
        f"Symbol '{symbol}' not found on {exchange}. "
        f"Check symbol spelling (e.g., RELIANCE, TCS, INFY)."
    )


async def resolve_security_id(
    client: INDstocksClient,
    symbol: str,
    exchange: str = "NSE",
) -> str:
    """Resolve a symbol to its raw security ID (e.g. ``"2885"``).

    Unlike :func:`resolve_scrip_code` which returns ``"NSE_2885"``,
    this returns just the numeric part needed for the order API's
    ``security_id`` field.
    """
    scrip = await resolve_scrip_code(client, symbol, exchange)
    # scrip format: "NSE_2885" → extract "2885"
    return scrip.split("_", 1)[1] if "_" in scrip else scrip
