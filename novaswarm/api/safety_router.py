"""FastAPI router for pre-trade safety checks, risk rules, and intraday circuit breaker status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import math
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from novaswarm.broker.models import OrderRequest, OrderType, Side, TradingSignal
from novaswarm.broker.paper_engine import get_shared_paper_engine
from novaswarm.config import NovaSwarmConfig
from novaswarm.constants import (
    PAPER_SAFETY_RULES,
    SAFETY_RULES,
    SafetyRules,
)
from novaswarm.execution.safety_checker import SafetyChecker
from novaswarm.learning.tracker import SECTOR_MAP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/safety", tags=["safety"])


class SafetySimulateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, description="Stock ticker (e.g. INFY, RELIANCE)")
    action: str = Field("BUY", description="BUY or SELL")
    quantity: int = Field(..., ge=1, description="Order share quantity")
    price: float = Field(..., gt=0, description="Estimated price per share")
    order_type: str = Field("MARKET", description="MARKET or LIMIT")
    stop_loss: Optional[float] = Field(None, description="Proposed stop loss price")
    target: Optional[float] = Field(None, description="Proposed profit target price")
    confidence: Optional[int] = Field(80, ge=0, le=100, description="AI agent confidence 0-100")


class AccountContext(BaseModel):
    portfolio_value: float
    available_cash: float
    open_positions_count: int
    max_allowed_positions: int
    sector: str
    projected_sector_concentration_pct: float


class SafetySimulateResponse(BaseModel):
    passed: bool
    rejections: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    reason: str = ""
    simulated_order_value: float
    simulated_position_pct: float
    risk_pct: float
    max_allowed_quantity: int
    account_context: AccountContext


@router.get("/rules")
async def get_safety_rules() -> dict:
    """Return frozen immutable risk parameters for the current trading mode."""
    config = NovaSwarmConfig()
    is_paper = config.trading_mode == "paper"
    active_rules: SafetyRules = PAPER_SAFETY_RULES if is_paper else SAFETY_RULES

    rules_dict = {
        "max_position_pct": active_rules.max_position_pct,
        "max_daily_loss_pct": active_rules.max_daily_loss_pct,
        "max_weekly_loss_pct": active_rules.max_weekly_loss_pct,
        "max_monthly_loss_pct": active_rules.max_monthly_loss_pct,
        "max_open_positions": active_rules.max_open_positions,
        "max_lots_per_position": active_rules.max_lots_per_position,
        "max_order_value_inr": active_rules.max_order_value_inr,
        "max_orders_per_minute": active_rules.max_orders_per_minute,
        "require_stop_loss": active_rules.require_stop_loss,
        "min_stop_loss_pct": active_rules.min_stop_loss_pct,
        "min_confidence_pct": active_rules.min_confidence_pct,
        "market_hours_only": active_rules.market_hours_only,
        "cool_down_after_loss_minutes": active_rules.cool_down_after_loss_minutes,
        "no_naked_option_selling": active_rules.no_naked_option_selling,
        "auto_shutdown_on_api_failure_minutes": active_rules.auto_shutdown_on_api_failure_minutes,
        "max_sector_concentration_pct": config.max_sector_concentration_pct,
    }

    return {
        "mode": config.trading_mode,
        "rules": rules_dict,
    }


@router.post("/simulate", response_model=SafetySimulateResponse)
async def simulate_safety(req: SafetySimulateRequest) -> SafetySimulateResponse:
    """Simulate order validation against the 16 active safety rules before execution."""
    config = NovaSwarmConfig()
    paper = get_shared_paper_engine()
    snapshot = paper.get_snapshot()

    portfolio_val = float(snapshot.total_value)
    available_cash = float(snapshot.cash)
    order_val = round(req.quantity * req.price, 2)
    position_pct = round((order_val / portfolio_val * 100), 2) if portfolio_val > 0 else 0.0

    rules = PAPER_SAFETY_RULES if config.trading_mode == "paper" else SAFETY_RULES
    checker = SafetyChecker(
        rules=rules,
        max_sector_concentration_pct=config.max_sector_concentration_pct,
    )

    side = Side.BUY if req.action.upper() == "BUY" else Side.SELL
    order = OrderRequest(
        symbol=req.symbol.upper(),
        side=side,
        quantity=Decimal(req.quantity),
        price=float(req.price),
        order_type=OrderType.LIMIT if req.order_type.upper() == "LIMIT" else OrderType.MARKET,
        trigger_price=float(req.stop_loss) if req.stop_loss else None,
    )

    signal = TradingSignal(
        symbol=req.symbol.upper(),
        action=req.action.upper(),
        confidence=req.confidence or 80,
        entry_price=float(req.price),
        stop_loss=float(req.stop_loss) if req.stop_loss else None,
        target=float(req.target) if req.target else None,
    )

    funds = paper.get_funds()
    result = checker.validate(
        order=order,
        signal=signal,
        positions=snapshot.positions,
        funds=funds,
        portfolio_value=portfolio_val,
    )

    # Sector calculation
    symbol_upper = req.symbol.upper()
    sector = SECTOR_MAP.get(symbol_upper, "General")
    sector_value = sum(
        float(p.quantity) * (p.last_price or p.average_price)
        for p in snapshot.positions
        if SECTOR_MAP.get(p.symbol.upper(), "General") == sector and p.quantity > 0
    )
    if side == Side.BUY:
        sector_value += order_val
    proj_sector_pct = round((sector_value / portfolio_val * 100), 2) if portfolio_val > 0 else 0.0

    # Max allowed quantity based on max_position_pct and max_order_value_inr
    max_capital_for_pos = min(portfolio_val * rules.max_position_pct, rules.max_order_value_inr)
    max_qty = max(1, math.floor(max_capital_for_pos / req.price)) if req.price > 0 else 0

    warnings = []
    if proj_sector_pct > (config.max_sector_concentration_pct * 100 * 0.8):
        warnings.append(f"Sector {sector} concentration is reaching {proj_sector_pct:.1f}%")

    risk_pct = round((abs(req.price - (req.stop_loss or req.price * 0.98)) / req.price * 100), 2)

    return SafetySimulateResponse(
        passed=result.passed,
        rejections=result.rejections,
        warnings=warnings,
        reason=result.reason,
        simulated_order_value=order_val,
        simulated_position_pct=position_pct,
        risk_pct=risk_pct,
        max_allowed_quantity=max_qty,
        account_context=AccountContext(
            portfolio_value=portfolio_val,
            available_cash=available_cash,
            open_positions_count=len(snapshot.positions),
            max_allowed_positions=rules.max_open_positions,
            sector=sector,
            projected_sector_concentration_pct=proj_sector_pct,
        ),
    )


@router.get("/status")
async def get_safety_status() -> dict:
    """Current intraday safety monitor: daily drawdown limits, market hours, and rate limits."""
    config = NovaSwarmConfig()
    paper = get_shared_paper_engine()
    snapshot = paper.get_snapshot()

    rules = PAPER_SAFETY_RULES if config.trading_mode == "paper" else SAFETY_RULES
    portfolio_val = float(snapshot.total_value)
    day_pnl = float(snapshot.day_pnl)
    day_loss_limit = round(portfolio_val * rules.max_daily_loss_pct, 2)

    loss_usage_pct = 0.0
    if day_pnl < 0 and day_loss_limit > 0:
        loss_usage_pct = round((abs(day_pnl) / day_loss_limit) * 100, 1)

    circuit_breaker_tripped = (day_pnl < 0) and (abs(day_pnl) >= day_loss_limit)

    # Calculate IST market hours
    now_utc = datetime.now(timezone.utc)
    ist_now = now_utc + timedelta(hours=5, minutes=30)
    ist_time_str = ist_now.strftime("%H:%M")
    is_weekday = ist_now.weekday() < 5
    is_open = is_weekday and ("09:15" <= ist_time_str <= "15:30")

    return {
        "circuit_breaker_tripped": circuit_breaker_tripped,
        "day_pnl": day_pnl,
        "day_loss_limit_inr": day_loss_limit,
        "daily_loss_usage_pct": loss_usage_pct,
        "open_positions_count": len(snapshot.positions),
        "max_open_positions": rules.max_open_positions,
        "market_hours": {
            "is_open": is_open,
            "ist_time": ist_time_str,
            "market_open": "09:15",
            "market_close": "15:30",
        },
        "rate_limits": {
            "orders_last_minute": 0,
            "max_per_minute": rules.max_orders_per_minute,
        },
    }
