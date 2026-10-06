"""LangChain tool definitions for market data and technical indicators.

Native implementation with typed models and zero external framework dependencies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional
from langchain_core.tools import tool

from novaswarm.data.pipeline import (
    get_fundamentals as _get_fundamentals,
    get_news as _get_news,
    get_stock_data as _get_stock_data,
)
from novaswarm.indicators.engine import get_indicators as _get_indicators


@tool
def get_stock_data(
    symbol: Annotated[str, "Ticker symbol of the company or cryptocurrency, e.g. RELIANCE, TCS, AAPL"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """Retrieve historical stock OHLCV price data formatted as CSV for a given ticker symbol and date range."""
    try:
        return _get_stock_data(symbol, start_date, end_date)
    except Exception as exc:
        return f"Stock data error for {symbol}: {exc}"


@tool
def get_indicators(
    symbol: Annotated[str, "Ticker symbol of the asset, e.g. RELIANCE, TCS"],
    indicator: Annotated[str, "Technical indicator to compute (e.g. atr, rsi, macd, close_50_sma, boll) or comma-separated list"],
    curr_date: Annotated[str, "Reference trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Lookback window in days (default 30)"] = 30,
) -> str:
    """Compute and format technical indicators for a given ticker symbol up to curr_date."""
    try:
        return _get_indicators(symbol, indicator, curr_date, look_back_days)
    except Exception as exc:
        return f"Indicator error for {symbol}: {exc}"


@tool
def get_fundamentals(
    symbol: Annotated[str, "Ticker symbol of the company"],
) -> str:
    """Retrieve company profile, market capitalization, P/E ratio, 52-week range, and valuation fundamentals."""
    try:
        import pandas as pd
        fund = _get_fundamentals(symbol)
        if not fund:
            return f"No fundamentals available for {symbol}."

        pe_str = f"PE Ratio: {float(fund.pe_ratio):.2f}" if (fund.pe_ratio is not None and not pd.isna(fund.pe_ratio)) else "PE Ratio: N/A"
        mcap_val = float(fund.market_cap) if (fund.market_cap is not None and not pd.isna(fund.market_cap)) else 0.0
        mcap_str = f"Market Cap: ₹{mcap_val:,.0f}" if mcap_val > 0 else "Market Cap: N/A"
        if fund.fifty_two_week_low is not None and not pd.isna(fund.fifty_two_week_low) and fund.fifty_two_week_high is not None and not pd.isna(fund.fifty_two_week_high):
            range_str = f"52-Week Range: ₹{float(fund.fifty_two_week_low):.2f} - ₹{float(fund.fifty_two_week_high):.2f}"
        else:
            range_str = "52-Week Range: N/A"

        lines = [
            f"Symbol: {fund.symbol}",
            f"Company: {fund.company_name}",
            f"Sector: {fund.sector or 'N/A'} | Industry: {fund.industry or 'N/A'}",
            mcap_str,
            pe_str,
            range_str,
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Fundamentals error for {symbol}: {exc}"


@tool
def get_news(
    symbol: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[Optional[str], "Current date in YYYY-MM-DD format"] = None,
    look_back_days: Annotated[int, "Number of days of news to search (default 7)"] = 7,
) -> str:
    """Retrieve recent financial and business news headlines for a ticker symbol."""
    try:
        articles = _get_news(symbol, curr_date, look_back_days)
        if not articles:
            return f"No recent news found for {symbol}."
        lines = []
        for art in articles[:5]:
            if isinstance(art.published_at, datetime):
                pub = f" ({art.published_at.strftime('%Y-%m-%d')})"
            elif art.published_at:
                pub = f" ({str(art.published_at)[:10]})"
            else:
                pub = ""
            source_desc = art.summary or getattr(art, "publisher", "") or getattr(art, "provider", "")
            lines.append(f"- {art.title}{pub}: {source_desc}")
        return "\n".join(lines)
    except Exception as exc:
        return f"News error for {symbol}: {exc}"


# ── Crypto Intelligence Tools ────────────────────────────────────────────────


from novaswarm.data.crypto import (
    get_blockchain_stats as _get_blockchain_stats,
    get_address_activity as _get_address_activity,
    get_token_fundamentals as _get_token_fundamentals,
    get_defi_tvl as _get_defi_tvl,
    get_chain_tvl_overview as _get_chain_tvl_overview,
    get_funding_rates as _get_funding_rates,
    get_open_interest as _get_open_interest,
    get_long_short_ratio as _get_long_short_ratio,
)


@tool
def get_blockchain_stats(
    coin: Annotated[str, "Cryptocurrency symbol (e.g. BTC, ETH, SOL)"],
) -> str:
    """Fetch on-chain network metrics (blocks, transactions, hash rate, difficulty) for a blockchain."""
    try:
        return _get_blockchain_stats(coin)
    except Exception as exc:
        return f"Blockchain stats error for {coin}: {exc}"


@tool
def get_address_activity(
    coin: Annotated[str, "Cryptocurrency symbol (e.g. BTC, ETH)"],
    address: Annotated[str, "Public blockchain wallet or contract address"],
) -> str:
    """Fetch recent transaction count and balance activity for a specific blockchain address."""
    try:
        return _get_address_activity(coin, address)
    except Exception as exc:
        return f"Address activity error for {address}: {exc}"


@tool
def get_token_fundamentals(
    token: Annotated[str, "DeFi protocol or token name (e.g. uniswap, aave, lido)"],
) -> str:
    """Retrieve DeFi protocol fundamentals, categories, chains, and Total Value Locked (TVL)."""
    try:
        return _get_token_fundamentals(token)
    except Exception as exc:
        return f"DeFi fundamentals error for {token}: {exc}"


@tool
def get_defi_tvl(
    protocol: Annotated[str, "DeFi protocol identifier (e.g. makerdao, curve)"],
) -> str:
    """Retrieve Total Value Locked (TVL) metrics for a given DeFi protocol."""
    try:
        return _get_defi_tvl(protocol)
    except Exception as exc:
        return f"DeFi TVL error for {protocol}: {exc}"


@tool
def get_chain_tvl_overview(
    chain: Annotated[str, "Layer-1 or Layer-2 chain name (e.g. Ethereum, Solana, Arbitrum)"],
) -> str:
    """Fetch ecosystem-wide Total Value Locked (TVL) for a specific blockchain network."""
    try:
        return _get_chain_tvl_overview(chain)
    except Exception as exc:
        return f"Chain TVL error for {chain}: {exc}"


@tool
def get_funding_rates(
    symbol: Annotated[str, "Crypto perpetual futures symbol (e.g. BTCUSDT, ETHUSDT)"],
) -> str:
    """Fetch recent funding rates and annualized cost-of-carry for crypto perpetual futures."""
    try:
        return _get_funding_rates(symbol)
    except Exception as exc:
        return f"Funding rate error for {symbol}: {exc}"


@tool
def get_open_interest(
    symbol: Annotated[str, "Crypto perpetual futures symbol (e.g. BTCUSDT)"],
) -> str:
    """Fetch current aggregate open interest in contracts for crypto perpetual contracts."""
    try:
        return _get_open_interest(symbol)
    except Exception as exc:
        return f"Open interest error for {symbol}: {exc}"


@tool
def get_long_short_ratio(
    symbol: Annotated[str, "Crypto perpetual futures symbol (e.g. BTCUSDT)"],
) -> str:
    """Fetch top trader account long/short position ratio for crypto futures."""
    try:
        return _get_long_short_ratio(symbol)
    except Exception as exc:
        return f"Long/Short ratio error for {symbol}: {exc}"

