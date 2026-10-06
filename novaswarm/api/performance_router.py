"""FastAPI router for portfolio performance metrics, equity curves, model accuracy, and learning curve analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from novaswarm.api.db_utils import get_safe_supabase
from novaswarm.broker.paper_engine import get_shared_paper_engine
from novaswarm.config import NovaSwarmConfig
from novaswarm.db.repositories import PredictionRepository, SnapshotRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/performance", tags=["performance"])


class PerformanceMetricsResponse(BaseModel):
    portfolio_value: float
    initial_capital: float
    total_return_pct: float
    day_pnl: float
    day_pnl_pct: float
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 1.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    mode: str = "paper"


class SnapshotItem(BaseModel):
    date: str
    equity: float
    portfolio_value: float
    cash: float
    day_pnl: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    drawdown_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


class DailySnapshotsResponse(BaseModel):
    snapshots: List[SnapshotItem]


class ModelAccuracyItem(BaseModel):
    model_name: str
    role: str
    total_predictions: int = 0
    accurate_predictions: int = 0
    correct_predictions: int = 0
    accuracy_pct: float = 0.0
    avg_latency_ms: int = 0
    avg_confidence: float = 0.0


class ModelAccuracyResponse(BaseModel):
    models: List[ModelAccuracyItem]


@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics() -> PerformanceMetricsResponse:
    """Get high-level portfolio KPIs: total equity, returns, win rate, Sharpe ratio, drawdown."""
    config = NovaSwarmConfig()
    paper = get_shared_paper_engine()
    snapshot = paper.get_snapshot()

    portfolio_value = float(snapshot.total_value)
    initial_cap = float(config.initial_paper_capital)
    total_return_pct = round(((portfolio_value - initial_cap) / initial_cap) * 100, 2)
    day_pnl = float(snapshot.day_pnl)
    day_pnl_pct = round((day_pnl / portfolio_value) * 100, 2) if portfolio_value > 0 else 0.0

    win_rate = 0.0
    total_trades = 0
    winning_trades = 0
    losing_trades = 0
    profit_factor = 1.0
    sharpe_ratio = 0.0
    max_dd = 0.0

    client = get_safe_supabase()
    if client:
        try:
            res = client.table("trades").select("pnl").execute()
            rows = res.data or []
            pnls = [float(r["pnl"]) for r in rows if r.get("pnl") is not None]
            total_trades = len(rows)
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            winning_trades = len(wins)
            losing_trades = len(losses)
            if winning_trades + losing_trades > 0:
                win_rate = round(winning_trades / (winning_trades + losing_trades) * 100, 1)

            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            if gross_loss > 0:
                profit_factor = round(gross_profit / gross_loss, 2)
            elif gross_profit > 0:
                profit_factor = round(gross_profit, 2)

            if len(pnls) >= 5:
                import numpy as np
                mean_pnl = float(np.mean(pnls))
                std_pnl = float(np.std(pnls))
                sharpe_ratio = round(float(mean_pnl / std_pnl * (252 ** 0.5)), 2) if std_pnl > 0 else 0.0

                # Compute true peak-to-trough max drawdown percentage from equity curve
                cum_equity = initial_cap
                peak_equity = initial_cap
                max_dd_val = 0.0
                for pnl in pnls:
                    cum_equity += pnl
                    if cum_equity > peak_equity:
                        peak_equity = cum_equity
                    if peak_equity > 0:
                        dd = (peak_equity - cum_equity) / peak_equity * 100.0
                        if dd > max_dd_val:
                            max_dd_val = dd
                max_dd = round(max_dd_val, 2)
            else:
                sharpe_ratio = 0.0
                max_dd = 0.0
        except Exception as exc:
            logger.debug("Error computing metrics from DB: %s", exc)

    return PerformanceMetricsResponse(
        portfolio_value=portfolio_value,
        initial_capital=initial_cap,
        total_return_pct=total_return_pct,
        day_pnl=day_pnl,
        day_pnl_pct=day_pnl_pct,
        win_rate=win_rate,
        sharpe_ratio=sharpe_ratio,
        max_drawdown_pct=max_dd,
        profit_factor=profit_factor,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        mode=config.trading_mode,
    )


@router.get("/daily-snapshots", response_model=DailySnapshotsResponse)
async def get_daily_snapshots(
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> DailySnapshotsResponse:
    """Fetch daily equity and P&L snapshots for charting visual equity curves."""
    today = datetime.now(timezone.utc).date()
    client = get_safe_supabase()
    snapshots_list: List[SnapshotItem] = []

    if client:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=days)
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
            repo = SnapshotRepository(client)
            db_snaps = repo.get_range(s_date, e_date)
            for s in db_snaps:
                p_val = float(s.portfolio_value)
                snapshots_list.append(
                    SnapshotItem(
                        date=s.date.isoformat(),
                        equity=p_val,
                        portfolio_value=p_val,
                        cash=float(s.cash),
                        day_pnl=float(s.day_pnl),
                        realized_pnl=float(s.day_pnl),
                        unrealized_pnl=0.0,
                        drawdown_pct=float(s.max_drawdown_pct or 0.0),
                        total_trades=s.total_trades,
                        winning_trades=s.winning_trades,
                        losing_trades=s.losing_trades,
                    )
                )
        except Exception as exc:
            logger.warning("Error querying daily snapshots: %s", exc)

    # If no snapshots stored in DB, generate baseline points ending today
    if not snapshots_list:
        config = NovaSwarmConfig()
        paper = get_shared_paper_engine()
        snap = paper.get_snapshot()
        current_val = float(snap.total_value)
        current_cash = float(snap.cash)
        current_pnl = float(snap.day_pnl)

        # Generate a realistic 7-day initial sequence for empty databases
        num_days = min(days, 7)
        for i in range(num_days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            if i == 0:
                p_val = current_val
                p_pnl = current_pnl
            else:
                p_val = float(config.initial_paper_capital)
                p_pnl = 0.0

            snapshots_list.append(
                SnapshotItem(
                    date=d,
                    equity=p_val,
                    portfolio_value=p_val,
                    cash=current_cash,
                    day_pnl=p_pnl,
                    realized_pnl=p_pnl,
                    unrealized_pnl=0.0,
                    drawdown_pct=0.0,
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                )
            )

    return DailySnapshotsResponse(snapshots=snapshots_list)


@router.get("/models", response_model=ModelAccuracyResponse)
async def get_model_accuracy() -> ModelAccuracyResponse:
    """Breakdown of prediction accuracy, sample size, and latency across active LLMs."""
    known_models = [
        {"model_name": "claude-3-5-sonnet", "role": "Analyst & Deep Reasoning", "default_latency": 1380},
        {"model_name": "gemini-2.0-flash", "role": "Scanner & Fast Triage", "default_latency": 450},
        {"model_name": "perplexity-sonar", "role": "Real-time News & Macro", "default_latency": 1550},
        {"model_name": "xai-grok", "role": "Social Sentiment & Catalyst", "default_latency": 920},
    ]

    client = get_safe_supabase()
    results: List[ModelAccuracyItem] = []

    for item in known_models:
        m_name = item["model_name"]
        role = item["role"]
        total = 0
        correct = 0
        acc_pct = 0.0
        lat = item["default_latency"]
        conf = 0.0

        if client:
            try:
                repo = PredictionRepository(client)
                stats = repo.get_model_accuracy(m_name)
                if stats and stats.get("total", 0) > 0:
                    total = stats["total"]
                    correct = stats.get("correct", 0)
                    acc_pct = round(stats.get("accuracy", 0.0) * 100, 1)
                    conf = round(float(stats.get("avg_confidence", 0.0)), 1)
                    lat = int(stats.get("avg_latency_ms", lat))
            except Exception as exc:
                logger.debug("Error checking accuracy for model %s: %s", m_name, exc)

        results.append(
            ModelAccuracyItem(
                model_name=m_name,
                role=role,
                total_predictions=total,
                accurate_predictions=correct,
                correct_predictions=correct,
                accuracy_pct=acc_pct,
                avg_latency_ms=lat,
                avg_confidence=conf,
            )
        )

    return ModelAccuracyResponse(models=results)


@router.get("/learning")
async def get_learning_curve() -> dict:
    """Fetch AI strategy adaptation history, sector accuracy, regime performance, and insights."""
    try:
        from novaswarm.learning.tracker import (
            generate_learning_insights,
            get_confidence_calibration,
            get_regime_performance,
            get_sector_performance,
            get_stop_loss_analysis,
        )

        insights_text = generate_learning_insights()
        sector_perf = get_sector_performance()
        regime_perf = get_regime_performance()
        calibration = get_confidence_calibration()
        stop_loss = get_stop_loss_analysis()

        return {
            "active_version": "v1.0.0",
            "evolution_count": 0,
            "learning_rate": 0.05,
            "insights": [line for line in insights_text.split("\n") if line.strip()],
            "sector_performance": sector_perf,
            "regime_performance": regime_perf,
            "confidence_calibration": calibration,
            "stop_loss_analysis": stop_loss,
            "history": [],
        }
    except Exception as exc:
        logger.debug("Error generating learning curve data: %s", exc)
        return {
            "active_version": "v1.0.0",
            "evolution_count": 0,
            "learning_rate": 0.05,
            "insights": ["AI learning engine initialized. Collecting live market observations."],
            "sector_performance": [],
            "regime_performance": {},
            "confidence_calibration": [],
            "stop_loss_analysis": {},
            "history": [],
        }
