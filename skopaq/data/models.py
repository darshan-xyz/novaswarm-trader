"""Data models and DataFrame schemas for SkopaqTrader market data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict, model_validator


class QuoteData(BaseModel):
    """Real-time market quote."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    exchange: str = "NSE"
    ltp: float = Field(..., description="Last traded price")
    open: float
    high: float
    low: float
    close: float = Field(..., description="Previous session close")
    volume: int
    change: float
    change_pct: float
    bid: float = 0.0
    ask: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: str = "unknown"

    def to_csv_row(self) -> str:
        """Format as CSV string matching legacy consumer expectations."""
        return (
            f"{self.symbol},{self.ltp:.2f},{self.open:.2f},{self.high:.2f},"
            f"{self.low:.2f},{self.close:.2f},{self.volume},"
            f"{self.change:.2f},{self.change_pct:.2f}"
        )

    def to_markdown(self) -> str:
        """Format as clean markdown card for agents."""
        return (
            f"### Quote: {self.symbol} ({self.exchange})\n"
            f"- **LTP**: ₹{self.ltp:,.2f} ({self.change:+,.2f} / {self.change_pct:+.2f}%)\n"
            f"- **Day Range**: ₹{self.low:,.2f} - ₹{self.high:,.2f} | **Open**: ₹{self.open:,.2f} | **Prev Close**: ₹{self.close:,.2f}\n"
            f"- **Volume**: {self.volume:,} | **Provider**: {self.provider}\n"
        )


class CompanyFundamentals(BaseModel):
    """Company fundamental metrics."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    company_name: str = ""
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    pe_ratio_ttm: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    pb_ratio: Optional[float] = None
    eps_ttm: Optional[float] = None
    forward_eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    fifty_day_average: Optional[float] = None
    two_hundred_day_average: Optional[float] = None
    revenue_ttm: Optional[float] = None
    gross_profit: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    book_value: Optional[float] = None
    free_cash_flow: Optional[float] = None
    financial_statements: dict[str, Any] = Field(default_factory=dict)
    provider: str = "yfinance"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def sync_pe_pb(self) -> CompanyFundamentals:
        if self.pe_ratio is not None and self.pe_ratio_ttm is None:
            self.pe_ratio_ttm = self.pe_ratio
        elif self.pe_ratio_ttm is not None and self.pe_ratio is None:
            self.pe_ratio = self.pe_ratio_ttm

        if self.pb_ratio is not None and self.price_to_book is None:
            self.price_to_book = self.pb_ratio
        elif self.price_to_book is not None and self.pb_ratio is None:
            self.pb_ratio = self.price_to_book
        return self

    def to_markdown(self) -> str:
        """Format as institutional fundamental report for Fundamental Analyst."""
        pe_val = self.pe_ratio_ttm or self.pe_ratio
        pb_val = self.price_to_book or self.pb_ratio
        lines = [
            f"# Company Fundamentals: {self.company_name or self.symbol} ({self.symbol})",
            f"Sector: {self.sector or 'N/A'} | Industry: {self.industry or 'N/A'}",
            f"Market Cap: ₹{self.market_cap:,.0f}" if self.market_cap else "Market Cap: N/A",
            f"P/E (TTM): {pe_val:.2f}" if pe_val else "P/E (TTM): N/A",
            f"Forward P/E: {self.forward_pe:.2f}" if self.forward_pe else "Forward P/E: N/A",
            f"Price to Book: {pb_val:.2f}" if pb_val else "P/B: N/A",
            f"EPS (TTM): ₹{self.eps_ttm:.2f}" if self.eps_ttm else "EPS: N/A",
            f"ROE: {self.return_on_equity * 100:.2f}%" if self.return_on_equity else "ROE: N/A",
            f"Profit Margin: {self.profit_margin * 100:.2f}%" if self.profit_margin else "Profit Margin: N/A",
            f"52-Week Range: ₹{self.fifty_two_week_low} - ₹{self.fifty_two_week_high}",
            f"Debt to Equity: {self.debt_to_equity:.2f}" if self.debt_to_equity else "Debt/Equity: N/A",
            f"Free Cash Flow: ₹{self.free_cash_flow:,.0f}" if self.free_cash_flow else "FCF: N/A",
        ]
        return "\n".join(lines)


class NewsArticle(BaseModel):
    """News and media article."""

    model_config = ConfigDict(extra="ignore")

    title: str
    summary: str = ""
    publisher: str = "Unknown"
    url: str = ""
    published_at: Optional[Union[datetime, str]] = None
    symbol: Optional[str] = None
    sentiment_score: Optional[float] = None
    provider: str = "yfinance"

    def to_markdown(self) -> str:
        date_str = (
            self.published_at.strftime("%Y-%m-%d %H:%M")
            if isinstance(self.published_at, datetime)
            else (str(self.published_at) if self.published_at else "Recent")
        )
        md = f"### {self.title}\n*Source: {self.publisher} | Published: {date_str}*\n"
        if self.summary:
            md += f"{self.summary}\n"
        if self.url:
            md += f"Link: {self.url}\n"
        return md


def validate_ohlcv_dataframe(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
    """Validate and enforce canonical OHLCV DataFrame schema.

    Schema Guarantee:
    - Index: DatetimeIndex named 'Date', tz-naive, sorted chronologically ascending.
    - Columns: ['Open', 'High', 'Low', 'Close', 'Volume']
    - Dtypes: Open, High, Low, Close are float64; Volume is int64 or float64.
    - Zero duplicate timestamps.
    """
    if df is None or df.empty:
        raise ValueError(f"OHLCV DataFrame for '{symbol}' is empty")

    res = df.copy()

    # Flatten MultiIndex columns if present (e.g. from yfinance download)
    if isinstance(res.columns, pd.MultiIndex):
        res.columns = res.columns.get_level_values(0)

    # Normalize Date index/column
    if "Date" in res.columns:
        res["Date"] = pd.to_datetime(res["Date"])
        res.set_index("Date", inplace=True)
    elif "date" in res.columns:
        res["date"] = pd.to_datetime(res["date"])
        res.set_index("date", inplace=True)
    elif not isinstance(res.index, pd.DatetimeIndex):
        res.index = pd.to_datetime(res.index)

    res.index.name = "Date"

    # Strip timezone if present
    if res.index.tz is not None:
        res.index = res.index.tz_localize(None)

    # Validate required columns
    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required_cols if c not in res.columns]
    if missing:
        # Check case-insensitive mapping
        col_map = {c.lower(): c for c in res.columns}
        for req in missing:
            if req.lower() in col_map:
                res.rename(columns={col_map[req.lower()]: req}, inplace=True)

    missing = [c for c in required_cols if c not in res.columns]
    if missing:
        raise ValueError(f"OHLCV data missing required columns: {missing}")

    # Enforce dtypes
    for col in ["Open", "High", "Low", "Close"]:
        res[col] = pd.to_numeric(res[col], errors="coerce").astype(float)
    res["Volume"] = pd.to_numeric(res["Volume"], errors="coerce").fillna(0).astype(np.int64)

    # Deduplicate and sort chronologically ascending
    res = res[~res.index.duplicated(keep="last")]
    res.sort_index(ascending=True, inplace=True)
    res.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    return res[required_cols]
