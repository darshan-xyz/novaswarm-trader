"""FastAPI router for querying trade records, trade details, and aggregate performance stats."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from skopaq.api.db_utils import get_safe_supabase
from skopaq.db.models import TradeRecord
from skopaq.db.repositories import PredictionRepository, TradeRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trades", tags=["trades"])


class TradeListResponse(BaseModel):
    trades: List[TradeRecord]
    total: int
    limit: int
    offset: int


class TradeStatsResponse(BaseModel):
    total_trades: int = 0
    paper_trades: int = 0
    live_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_realized_pnl: float = 0.0
    total_brokerage: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 1.0
    avg_pnl_per_trade: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0


@router.get("", response_model=TradeListResponse)
async def list_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    is_paper: Optional[bool] = None,
    strategy: Optional[str] = None,
) -> TradeListResponse:
    """Fetch paginated trade history with optional filtering by status, symbol, side, mode, and strategy."""
    client = get_safe_supabase()
    if not client:
        return TradeListResponse(trades=[], total=0, limit=limit, offset=offset)

    try:
        query = client.table("trades").select("*", count="exact")
        if symbol:
            query = query.eq("symbol", symbol.strip().upper())
        if side:
            query = query.eq("side", side.strip().upper())
        if status:
            query = query.eq("status", status.strip().upper())
        if is_paper is not None:
            query = query.eq("is_paper", is_paper)
        if strategy:
            query = query.eq("strategy_version", strategy.strip())

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        res = query.execute()

        rows = res.data or []
        total = res.count if res.count is not None else len(rows)
        trades = [TradeRecord(**row) for row in rows]
        return TradeListResponse(trades=trades, total=total, limit=limit, offset=offset)
    except Exception as exc:
        logger.warning("Error fetching trades: %s", exc)
        return TradeListResponse(trades=[], total=0, limit=limit, offset=offset)


@router.get("/summary/stats", response_model=TradeStatsResponse)
async def get_trade_stats() -> TradeStatsResponse:
    """Calculate aggregated win/loss statistics, P&L, brokerage, and profit factor."""
    client = get_safe_supabase()
    if not client:
        return TradeStatsResponse()

    try:
        res = client.table("trades").select("*").execute()
        rows = res.data or []
        if not rows:
            return TradeStatsResponse()

        total_trades = len(rows)
        paper_trades = sum(1 for r in rows if r.get("is_paper") is True)
        live_trades = total_trades - paper_trades

        pnls = [float(r["pnl"]) for r in rows if r.get("pnl") is not None]
        brokerages = [float(r.get("brokerage") or 0.0) for r in rows]

        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        win_count = len(winning)
        loss_count = len(losing)
        decided_count = win_count + loss_count

        win_rate = round(win_count / decided_count * 100, 1) if decided_count > 0 else 0.0
        total_pnl = round(sum(pnls), 2)
        total_brokerage = round(sum(brokerages), 2)
        net_pnl = round(total_pnl - total_brokerage, 2)

        gross_profit = round(sum(winning), 2)
        gross_loss = round(abs(sum(losing)), 2)
        profit_factor = (
            round(gross_profit / gross_loss, 2)
            if gross_loss > 0
            else (round(gross_profit, 2) if gross_profit > 0 else 1.0)
        )

        avg_pnl = round(total_pnl / len(pnls), 2) if pnls else 0.0
        largest_win = round(max(winning), 2) if winning else 0.0
        largest_loss = round(min(losing), 2) if losing else 0.0

        return TradeStatsResponse(
            total_trades=total_trades,
            paper_trades=paper_trades,
            live_trades=live_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            total_realized_pnl=total_pnl,
            total_brokerage=total_brokerage,
            net_pnl=net_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_pnl_per_trade=avg_pnl,
            largest_win=largest_win,
            largest_loss=largest_loss,
        )
    except Exception as exc:
        logger.warning("Error calculating trade stats: %s", exc)
        return TradeStatsResponse()


@router.get("/{trade_id}", response_model=Dict[str, Any])
async def get_trade_by_id(trade_id: str) -> Dict[str, Any]:
    """Retrieve full details for a trade record including linked model predictions."""
    try:
        uid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {trade_id}")

    client = get_safe_supabase()
    if not client:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    try:
        repo = TradeRepository(client)
        trade = repo.get_by_id(uid)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        pred_repo = PredictionRepository(client)
        predictions = pred_repo.get_by_trade(uid)

        result = trade.model_dump(mode="json")
        result["predictions"] = [p.model_dump(mode="json") for p in predictions]
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Error getting trade %s: %s", trade_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch trade: {exc}")
