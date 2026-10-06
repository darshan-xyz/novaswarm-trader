"""Primary Indian market data provider via INDstocks broker API."""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional
import pandas as pd

from novaswarm.broker.client import INDstocksClient
from novaswarm.broker.scrip_resolver import resolve_scrip_code
from novaswarm.broker.token_manager import TokenManager
from novaswarm.config import NovaSwarmConfig
from novaswarm.data.models import QuoteData, validate_ohlcv_dataframe
from novaswarm.data.symbols import to_indstocks_symbol

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class INDstocksError(Exception):
    """Base error for INDstocks provider failures."""


class INDstocksAuthError(INDstocksError):
    """INDstocks token missing, invalid, or expired."""


class INDstocksSymbolNotFoundError(INDstocksError):
    """Symbol not found in instruments master."""


def _run_async(coro):
    """Safely bridge async coroutines to sync callers across all event loop states."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)


class INDstocksDataProvider:
    """High-speed native provider for Indian equities market data."""

    def __init__(self, config: Optional[NovaSwarmConfig] = None):
        self._config = config or NovaSwarmConfig()
        self._token_mgr = TokenManager()

    def _get_client(self) -> INDstocksClient:
        token = self._config.indstocks_token.get_secret_value()
        if not token:
            raise INDstocksAuthError("NOVASWARM_INDSTOCKS_TOKEN is not configured")
        return INDstocksClient(self._config, self._token_mgr)

    def _date_to_epoch_ms(self, date_str: str) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=IST)
        return int(dt.timestamp() * 1000)

    async def get_historical_ohlcv_async(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1day",
    ) -> pd.DataFrame:
        """Fetch historical candles asynchronously from INDstocks."""
        bare_symbol, exchange = to_indstocks_symbol(symbol)
        client = self._get_client()

        try:
            async with client:
                scrip_code = await resolve_scrip_code(client, bare_symbol, exchange=exchange)
                start_ms = self._date_to_epoch_ms(start_date)
                end_ms = self._date_to_epoch_ms(end_date)

                candles = await client.get_historical(
                    scrip_code=scrip_code,
                    interval=interval,
                    start_time=start_ms,
                    end_time=end_ms,
                )
        except ValueError as exc:
            raise INDstocksSymbolNotFoundError(f"Symbol '{bare_symbol}' not found on {exchange}: {exc}") from exc
        except Exception as exc:
            raise INDstocksError(f"INDstocks historical request failed for {bare_symbol}: {exc}") from exc

        if not candles:
            raise INDstocksError(f"No candles returned for {bare_symbol} between {start_date} and {end_date}")

        records = []
        for c in candles:
            records.append({
                "Date": c.timestamp,
                "Open": c.open,
                "High": c.high,
                "Low": c.low,
                "Close": c.close,
                "Volume": c.volume,
            })

        df = pd.DataFrame(records)
        return validate_ohlcv_dataframe(df, symbol=bare_symbol)

    async def get_quote_async(self, symbol: str) -> QuoteData:
        """Fetch live quote asynchronously from INDstocks."""
        bare_symbol, exchange = to_indstocks_symbol(symbol)
        client = self._get_client()

        try:
            async with client:
                scrip_code = await resolve_scrip_code(client, bare_symbol, exchange=exchange)
                quote = await client.get_quote(scrip_code=scrip_code, symbol=bare_symbol)
        except Exception as exc:
            raise INDstocksError(f"INDstocks quote fetch failed for {bare_symbol}: {exc}") from exc

        return QuoteData(
            symbol=bare_symbol,
            exchange=exchange,
            ltp=quote.ltp,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            close=quote.close,
            volume=quote.volume,
            change=quote.change,
            change_pct=quote.change_pct,
            bid=quote.bid,
            ask=quote.ask,
            timestamp=quote.timestamp or datetime.now(timezone.utc),
            provider="indstocks",
        )

    def get_historical_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1day",
    ) -> pd.DataFrame:
        """Synchronous wrapper for get_historical_ohlcv_async."""
        return _run_async(self.get_historical_ohlcv_async(symbol, start_date, end_date, interval))

    def get_historical(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1day",
    ) -> pd.DataFrame:
        """Alias for get_historical_ohlcv."""
        return self.get_historical_ohlcv(symbol, start_date, end_date, interval)

    def get_quote(self, symbol: str) -> QuoteData:
        """Synchronous wrapper for get_quote_async."""
        return _run_async(self.get_quote_async(symbol))
