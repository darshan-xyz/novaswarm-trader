"""High-fidelity mock ASGI application for SkopaqTrader E2E opaque-box testing.

Implements all REST and SSE interface contracts defined in PROJECT.md and TEST_INFRA.md:
- Trades Router (/api/trades)
- Analysis Router & SSE Engine (/api/analysis)
- Memory Router (/api/memory)
- Performance Router (/api/performance)
- Safety Router (/api/safety)
- System Router (/api/system)
- Chat Router (/api/chat)
- Frontend Web Routes (/, /portfolio, /scanner, /analysis, /trades, /chat, /analytics, /settings)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import json
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field


class AnalysisStartRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    urgency: Optional[str] = "medium"
    lookback_days: Optional[int] = 30
    selected_analysts: Optional[List[str]] = None


class MemoryQueryRequest(BaseModel):
    role: str
    query: str
    top_k: Optional[int] = 3


class SafetySimulateRequest(BaseModel):
    symbol: str
    action: str
    quantity: int
    price: float
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    confidence: Optional[int] = 75


class HealingLogRequest(BaseModel):
    component: str
    event_type: str
    description: str
    action_taken: str
    resolved: bool = True
    metadata: Optional[Dict[str, Any]] = None


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatToolRequest(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None


def create_mock_app() -> FastAPI:
    """Create a fully functional mock FastAPI app matching all Skopaq contracts."""
    app = FastAPI(title="SkopaqTrader Mock API Server", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── IN-MEMORY REPOSITORIES & STATE ───────────────────────────────────────

    CANONICAL_MEMORY_ROLES = [
        "bull_memory",
        "bear_memory",
        "trader_memory",
        "invest_judge_memory",
        "risk_manager_memory",
    ]

    # Pre-populated trades database
    trades_db: List[Dict[str, Any]] = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 25,
            "price": 2850.0,
            "fill_price": 2851.5,
            "order_type": "MARKET",
            "product": "CNC",
            "order_id": "ord_rel_001",
            "status": "COMPLETE",
            "is_paper": True,
            "signal_source": "skopaq-swarm",
            "consensus_score": 88,
            "entry_reason": "Golden cross 50/200 SMA + robust retail margins",
            "exit_reason": "Target 1 achieved (+4.2%)",
            "pnl": 3000.0,
            "brokerage": 15.0,
            "slippage": 1.5,
            "strategy_version": "v1.0.0",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "closed_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "agent_decision": {"action": "BUY", "confidence": 88, "verdict": "BUY"},
            "model_signals": {"gemini": "BUY", "claude": "BUY", "grok": "NEUTRAL"},
            "opening_trade_id": None,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 15,
            "price": 3800.0,
            "fill_price": 3800.0,
            "order_type": "LIMIT",
            "product": "CNC",
            "order_id": "ord_tcs_002",
            "status": "COMPLETE",
            "is_paper": True,
            "signal_source": "skopaq-swarm",
            "consensus_score": 79,
            "entry_reason": "IT sector momentum + solid Q3 guidance",
            "exit_reason": "Stop loss hit on macro gap down",
            "pnl": -1200.0,
            "brokerage": 12.0,
            "slippage": 0.0,
            "strategy_version": "v1.0.0",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            "closed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "agent_decision": {"action": "BUY", "confidence": 79, "verdict": "BUY"},
            "model_signals": {"gemini": "BUY", "claude": "NEUTRAL", "perplexity": "BUY"},
            "opening_trade_id": None,
        },
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "symbol": "INFY",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 30,
            "price": 1820.0,
            "fill_price": 1822.0,
            "order_type": "MARKET",
            "product": "CNC",
            "order_id": "ord_infy_003",
            "status": "OPEN",
            "is_paper": True,
            "signal_source": "skopaq-swarm",
            "consensus_score": 82,
            "entry_reason": "Breakout above 1800 resistance",
            "exit_reason": None,
            "pnl": 450.0,
            "brokerage": 10.0,
            "slippage": 2.0,
            "strategy_version": "v1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "closed_at": None,
            "agent_decision": {"action": "BUY", "confidence": 82, "verdict": "BUY"},
            "model_signals": {"gemini": "BUY", "claude": "BUY"},
            "opening_trade_id": None,
        },
    ]

    # Pre-populated BM25 memories by role
    memories_db: Dict[str, List[Dict[str, Any]]] = {
        "bull_memory": [
            {
                "situation": "NIFTY trading near 200 DMA with heavy IT sector volume and positive earnings",
                "recommendation": "Look for breakout setups in tier-1 IT with ATR-based stops",
            },
            {
                "situation": "Strong institutional buying in private banks following RBI rate pause",
                "recommendation": "Initiate long positions on 15m pullback toward VWAP",
            },
        ],
        "bear_memory": [
            {
                "situation": "India VIX spiking above 20 with geopolitical escalation",
                "recommendation": "Tighten stops, reduce lot sizes by 50%, and avoid momentum longs",
            },
        ],
        "trader_memory": [
            {
                "situation": "Opening gap-up greater than 1.5% in high-beta equity",
                "recommendation": "Do not chase open; wait for 30-minute opening range breakout confirmation",
            },
        ],
        "invest_judge_memory": [
            {
                "situation": "Divergence between bullish technicals and negative macro news flow",
                "recommendation": "Favor capital preservation; require consensus score >= 80 before greenlighting",
            },
        ],
        "risk_manager_memory": [
            {
                "situation": "Portfolio daily drawdown reaching 2% before 12:00 IST",
                "recommendation": "Halt new entries for 60 minutes and review open positions",
            },
        ],
    }

    reflections_db: List[Dict[str, Any]] = [
        {
            "id": str(uuid4()),
            "symbol": "RELIANCE",
            "reflection": "PROFIT on RELIANCE: Strong multi-agent alignment on Q2 retail metrics led to clean 4.2% gain.",
            "pnl": 3000.0,
            "pnl_pct": 4.2,
            "trade_date": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        {
            "id": str(uuid4()),
            "symbol": "TCS",
            "reflection": "LOSS on TCS: Macro gap-down hit trailing stop. ATR stop protected capital from further loss.",
            "pnl": -1200.0,
            "pnl_pct": -2.1,
            "trade_date": (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d"),
            "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        },
    ]

    healing_events_db: List[Dict[str, Any]] = [
        {
            "id": "heal_001",
            "component": "broker",
            "event_type": "token_refresh",
            "description": "INDstocks access token refreshed successfully",
            "action_taken": "Re-authenticated session",
            "resolved": True,
            "metadata": {"token_lifetime_hours": 24},
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
        },
        {
            "id": "heal_002",
            "component": "circuit_breaker",
            "event_type": "drawdown_reset",
            "description": "Daily drawdown counter reset at market open 09:15 IST",
            "action_taken": "Cleared intraday loss accumulator",
            "resolved": True,
            "metadata": {"prev_day_pnl": 1800.0},
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
        },
    ]

    strategies_db: List[Dict[str, Any]] = [
        {
            "id": "strat_v100",
            "version": "v1.0.0",
            "dna_yaml": "strategy:\n  name: multi-agent-swing\n  max_positions: 5\n  risk_per_trade_pct: 0.02\n",
            "active": True,
            "backtest_sharpe": 2.15,
            "backtest_win_rate": 68.4,
            "backtest_max_dd": 4.5,
            "reason": "Production baseline deployment",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        }
    ]

    # Background analysis jobs store
    analysis_jobs: Dict[str, Dict[str, Any]] = {}
    analysis_job_events: Dict[str, List[Dict[str, Any]]] = {}

    # Chat sessions store
    chat_sessions: Dict[str, List[Dict[str, str]]] = {}

    # ── 1. SYSTEM OVERVIEW & HEALTH ──────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "mode": "paper",
            "token_valid": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/status")
    async def status_endpoint():
        return {
            "version": "0.1.0",
            "mode": "paper",
            "broker": {
                "name": "INDstocks",
                "base_url": "https://api.indstocks.com",
                "token_valid": True,
                "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=18)).isoformat(),
                "token_remaining": "18:00:00",
                "token_warning": None,
            },
            "services": {
                "supabase": True,
                "redis": True,
                "llms": {
                    "gemini": True,
                    "claude": True,
                    "perplexity": True,
                    "grok": True,
                },
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/portfolio")
    async def portfolio_endpoint():
        return {
            "total_value": 1045250.0,
            "cash": 425000.0,
            "positions_value": 620250.0,
            "day_pnl": 2250.0,
            "positions": [
                {
                    "symbol": "INFY",
                    "exchange": "NSE",
                    "quantity": 30,
                    "avg_price": 1820.0,
                    "current_price": 1835.0,
                    "pnl": 450.0,
                    "pnl_pct": 0.82,
                }
            ],
            "open_orders": [],
            "mode": "paper",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── 2. MARKET SCANNER ───────────────────────────────────────────────────

    @app.get("/api/scanner/status")
    async def scanner_status():
        return {
            "running": True,
            "cycle_count": 42,
            "last_cycle_at": datetime.now(timezone.utc).isoformat(),
            "watchlist_size": 50,
            "queue_size": 3,
            "screeners": ["gemini_flash", "perplexity_sonar", "grok_mini"],
        }

    @app.get("/api/scanner/candidates")
    async def scanner_candidates():
        candidates = [
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "urgency": "HIGH",
                "source": "Technicals + News",
                "screeners": ["gemini_flash", "perplexity_sonar"],
                "reason": "Breakout above ₹2840 with strong Q2 volume surge",
                "ltp": 2855.0,
                "change_pct": 2.4,
                "volume_ratio": 2.1,
                "gap_pct": 0.8,
            },
            {
                "symbol": "TCS",
                "exchange": "NSE",
                "urgency": "NORMAL",
                "source": "Technicals",
                "screeners": ["gemini_flash"],
                "reason": "Consolidation near 50-day EMA support",
                "ltp": 3820.0,
                "change_pct": 0.6,
                "volume_ratio": 1.2,
                "gap_pct": 0.1,
            },
        ]
        return {"candidates": candidates, "last_candidates": candidates}

    @app.post("/api/scanner/scan")
    async def trigger_scan():
        return {
            "status": "scan_initiated",
            "cycle": 43,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── 3. TRADES ROUTER ────────────────────────────────────────────────────

    @app.get("/api/trades")
    async def list_trades(
        limit: int = 50,
        offset: int = 0,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        is_paper: Optional[bool] = None,
        status: Optional[str] = None,
        strategy: Optional[str] = None,
    ):
        if limit <= 0:
            raise HTTPException(status_code=422, detail="limit must be greater than 0")
        if limit > 500:
            raise HTTPException(status_code=422, detail="limit cannot exceed 500")

        filtered = list(trades_db)

        if symbol:
            sym_clean = symbol.strip().upper()
            filtered = [t for t in filtered if t["symbol"] == sym_clean]
        if side:
            filtered = [t for t in filtered if t["side"].upper() == side.strip().upper()]
        if is_paper is not None:
            filtered = [t for t in filtered if t["is_paper"] == is_paper]
        if status:
            filtered = [t for t in filtered if t["status"].upper() == status.strip().upper()]
        if strategy:
            filtered = [t for t in filtered if t.get("strategy_version") == strategy]

        total = len(filtered)
        paginated = filtered[offset : offset + limit]

        return {
            "trades": paginated,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/trades/summary/stats")
    async def trade_stats():
        if not trades_db:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_realized_pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,
            }

        closed = [t for t in trades_db if t.get("pnl") is not None]
        total_closed = len(closed)
        winners = [t for t in closed if t["pnl"] > 0]
        losers = [t for t in closed if t["pnl"] <= 0]

        gross_profit = sum(t["pnl"] for t in winners)
        gross_loss = abs(sum(t["pnl"] for t in losers))
        total_realized = sum(t["pnl"] for t in closed)

        win_rate = (len(winners) / total_closed * 100.0) if total_closed > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        return {
            "total_trades": len(trades_db),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": round(win_rate, 2),
            "total_realized_pnl": round(total_realized, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2),
        }

    @app.get("/api/trades/{trade_id}")
    async def get_trade(trade_id: str):
        found = next((t for t in trades_db if t["id"] == trade_id), None)
        if not found:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        # Include model predictions if requested
        result = dict(found)
        result["model_predictions"] = [
            {
                "id": str(uuid4()),
                "trade_id": trade_id,
                "model_name": "claude-3-5-sonnet",
                "prediction": "BUY",
                "confidence": 85,
                "latency_ms": 1240,
            },
            {
                "id": str(uuid4()),
                "trade_id": trade_id,
                "model_name": "gemini-2.0-flash",
                "prediction": "BUY",
                "confidence": 80,
                "latency_ms": 380,
            },
        ]
        return result

    # ── 4. ANALYSIS ROUTER & SSE ENGINE ─────────────────────────────────────

    @app.post("/api/analysis", status_code=status.HTTP_202_ACCEPTED)
    async def start_analysis(req: AnalysisStartRequest):
        symbol = req.symbol.strip().upper()
        if not symbol or not re.match(r"^[A-Z0-9\-_.]+$", symbol):
            raise HTTPException(status_code=422, detail="Invalid symbol format")
        if req.lookback_days is not None and (req.lookback_days <= 0 or req.lookback_days > 365):
            raise HTTPException(status_code=422, detail="lookback_days must be between 1 and 365")

        job_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        job_state = {
            "job_id": job_id,
            "symbol": symbol,
            "status": "pending",
            "created_at": created_at,
            "lookback_days": req.lookback_days,
            "urgency": req.urgency,
            "agent_statuses": {
                "market_analyst": "pending",
                "social_analyst": "pending",
                "news_analyst": "pending",
                "fundamentals_analyst": "pending",
                "bull_researcher": "pending",
                "bear_researcher": "pending",
                "research_manager": "pending",
                "trader": "pending",
                "risk_judge": "pending",
            },
            "reports": {},
            "decision": None,
            "duration_seconds": 0.0,
            "error": None,
        }
        analysis_jobs[job_id] = job_state

        # Pre-seed the event timeline for the job
        events = [
            {
                "event": "job_started",
                "data": {"job_id": job_id, "symbol": symbol, "timestamp": created_at},
            },
            {
                "event": "agent_status",
                "data": {
                    "agent_id": "market_analyst",
                    "team": "analyst",
                    "status": "running",
                    "timestamp": created_at,
                },
            },
            {
                "event": "tool_call",
                "data": {
                    "agent_id": "market_analyst",
                    "tool_name": "get_indicators",
                    "tool_args": {"indicators": "rsi,macd,sma_50,sma_200"},
                    "tool_result": "RSI: 62.4, MACD: bullish cross",
                    "timestamp": created_at,
                },
            },
            {
                "event": "agent_chunk",
                "data": {
                    "agent_id": "market_analyst",
                    "chunk": "Technical setup for " + symbol + " shows bullish breakout.\n",
                    "timestamp": created_at,
                },
            },
            {
                "event": "agent_report",
                "data": {
                    "agent_id": "market_analyst",
                    "team": "analyst",
                    "report_markdown": "## Market Analysis\n- Trend: Bullish\n- Momentum: Positive",
                    "timestamp": created_at,
                },
            },
            {
                "event": "event_log",
                "data": {
                    "level": "INFO",
                    "message": "Analyst team completed reviews. Initiating debate.",
                    "timestamp": created_at,
                },
            },
            {
                "event": "decision_card",
                "data": {
                    "verdict": "BUY",
                    "confidence": 84,
                    "position_size": 25,
                    "entry_price": 2850.0,
                    "stop_loss": 2790.0,
                    "target": 2970.0,
                    "risk_reward_ratio": 2.0,
                    "reasoning": "Strong multi-agent alignment with favorable R:R ratio.",
                    "timestamp": created_at,
                },
            },
            {
                "event": "job_completed",
                "data": {
                    "job_id": job_id,
                    "final_verdict": "BUY",
                    "confidence": 84,
                    "duration_seconds": 2.45,
                    "timestamp": created_at,
                },
            },
        ]
        analysis_job_events[job_id] = events

        # Update final job state
        job_state["status"] = "completed"
        job_state["decision"] = events[-2]["data"]
        job_state["reports"]["market_analyst"] = "## Market Analysis\n- Trend: Bullish"
        job_state["duration_seconds"] = 2.45

        return {
            "job_id": job_id,
            "symbol": symbol,
            "status": "pending",
            "created_at": created_at,
        }

    @app.get("/api/analysis/{job_id}")
    async def get_analysis_job(job_id: str):
        job = analysis_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")
        return job

    @app.get("/api/analysis/{job_id}/stream")
    async def stream_analysis_events(job_id: str, request: Request):
        if job_id not in analysis_jobs:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

        events = analysis_job_events.get(job_id, [])

        async def event_generator():
            for ev in events:
                if await request.is_disconnected():
                    break
                payload = json.dumps(ev["data"])
                yield f"event: {ev['event']}\ndata: {payload}\n\n"
                await asyncio.sleep(0.01)

            # Emit keepalive heartbeat
            yield ": heartbeat\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── 5. MEMORY ROUTER ────────────────────────────────────────────────────

    @app.get("/api/memory/roles")
    async def get_memory_roles():
        return {
            "roles": CANONICAL_MEMORY_ROLES,
            "counts": {role: len(memories_db.get(role, [])) for role in CANONICAL_MEMORY_ROLES},
        }

    @app.get("/api/memory/role/{role_name}")
    async def get_memory_by_role(role_name: str, limit: int = 50):
        if role_name not in CANONICAL_MEMORY_ROLES:
            raise HTTPException(status_code=404, detail=f"Unknown memory role: {role_name}")

        entries = memories_db.get(role_name, [])[:limit]
        return {
            "role": role_name,
            "documents_count": len(entries),
            "memories": entries,
        }

    @app.post("/api/memory/query")
    async def query_memory(req: MemoryQueryRequest):
        if req.role not in CANONICAL_MEMORY_ROLES:
            raise HTTPException(status_code=404, detail=f"Unknown memory role: {req.role}")
        if req.top_k is not None and (req.top_k < 0 or req.top_k > 500):
            raise HTTPException(status_code=422, detail="top_k must be between 0 and 500")

        docs = memories_db.get(req.role, [])
        query_words = set(re.findall(r"\w+", req.query.lower()))

        results = []
        for doc in docs:
            doc_words = set(re.findall(r"\w+", doc["situation"].lower()))
            overlap = len(query_words & doc_words)
            sim_score = round(overlap / (len(query_words) or 1), 2)
            results.append({
                "situation": doc["situation"],
                "recommendation": doc["recommendation"],
                "similarity_score": min(sim_score, 1.0),
            })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        slice_limit = req.top_k if req.top_k is not None else 3
        top_results = results[:slice_limit]

        return {
            "role": req.role,
            "query": req.query,
            "results": top_results,
            "count": len(top_results),
        }

    @app.get("/api/memory/reflections")
    async def get_reflections(symbol: Optional[str] = None, limit: int = 20):
        if limit <= 0:
            raise HTTPException(status_code=422, detail="limit must be positive")
        filtered = list(reflections_db)
        if symbol:
            sym_clean = symbol.strip().upper()
            filtered = [r for r in filtered if r["symbol"] == sym_clean]
        return {
            "reflections": filtered[:limit],
            "count": len(filtered[:limit]),
            "total": len(filtered),
        }

    # ── 6. PERFORMANCE ROUTER ───────────────────────────────────────────────

    @app.get("/api/performance/metrics")
    async def get_performance_metrics():
        return {
            "portfolio_value": 1045250.0,
            "initial_capital": 1000000.0,
            "total_return_pct": 4.52,
            "day_pnl": 2250.0,
            "day_pnl_pct": 0.22,
            "win_rate": 66.7,
            "sharpe_ratio": 1.84,
            "max_drawdown_pct": 2.1,
            "profit_factor": 2.5,
            "total_trades": len(trades_db),
            "winning_trades": 2,
            "losing_trades": 1,
            "mode": "paper",
        }

    @app.get("/api/performance/daily-snapshots")
    async def get_daily_snapshots(days: int = 30, start_date: Optional[str] = None, end_date: Optional[str] = None):
        if days <= 0:
            raise HTTPException(status_code=422, detail="days must be positive")
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be before end_date")

        snapshots = []
        base_val = 1000000.0
        for i in range(min(days, 30), 0, -1):
            d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            pnl = 1500.0 if i % 2 == 0 else -600.0
            base_val += pnl
            snapshots.append({
                "date": d,
                "portfolio_value": round(base_val, 2),
                "cash": round(base_val * 0.4, 2),
                "day_pnl": pnl,
                "total_trades": 2,
                "winning_trades": 1 if pnl > 0 else 0,
                "losing_trades": 1 if pnl <= 0 else 0,
                "max_drawdown_pct": 1.2,
            })

        return {"snapshots": snapshots}

    @app.get("/api/performance/models")
    async def get_model_performance():
        return {
            "models": [
                {
                    "model_name": "claude-3-5-sonnet",
                    "role": "Analyst & Deep Reasoning",
                    "total_predictions": 85,
                    "accurate_predictions": 61,
                    "accuracy_pct": 71.8,
                    "avg_confidence": 82.4,
                    "avg_latency_ms": 1420,
                },
                {
                    "model_name": "gemini-2.0-flash",
                    "role": "Scanner & Fast Triage",
                    "total_predictions": 120,
                    "accurate_predictions": 82,
                    "accuracy_pct": 68.3,
                    "avg_confidence": 78.0,
                    "avg_latency_ms": 480,
                },
                {
                    "model_name": "perplexity-sonar",
                    "role": "Real-time News & Macro",
                    "total_predictions": 45,
                    "accurate_predictions": 31,
                    "accuracy_pct": 68.9,
                    "avg_confidence": 75.5,
                    "avg_latency_ms": 1650,
                },
                {
                    "model_name": "xai-grok",
                    "role": "Social Sentiment & Catalyst",
                    "total_predictions": 40,
                    "accurate_predictions": 26,
                    "accuracy_pct": 65.0,
                    "avg_confidence": 72.0,
                    "avg_latency_ms": 950,
                },
            ]
        }

    @app.get("/api/performance/learning")
    async def get_performance_learning():
        return {
            "learning_curve": [
                {"generation": 1, "win_rate": 58.0, "sharpe": 1.2},
                {"generation": 2, "win_rate": 62.5, "sharpe": 1.5},
                {"generation": 3, "win_rate": 66.7, "sharpe": 1.84},
            ],
            "insights": [
                "Position sizing scaled down during VIX > 18 reduced drawdown by 35%",
                "IT sector breakouts confirmed by volume ratio > 1.8 yield 74% win rate",
            ],
        }

    # ── 7. SAFETY ROUTER ────────────────────────────────────────────────────

    FROZEN_SAFETY_RULES = {
        "max_position_pct": 0.15,
        "max_daily_loss_pct": 0.03,
        "max_weekly_loss_pct": 0.07,
        "max_monthly_loss_pct": 0.12,
        "max_open_positions": 5,
        "max_lots_per_position": 5,
        "max_order_value_inr": 500000.0,
        "max_orders_per_minute": 20,
        "require_stop_loss": True,
        "min_stop_loss_pct": 0.02,
        "min_confidence_pct": 60,
        "market_hours_only": False,
        "cool_down_after_loss_minutes": 15,
        "max_sector_concentration_pct": 0.40,
    }

    @app.get("/api/safety/rules")
    async def get_safety_rules():
        return {"mode": "paper", "rules": FROZEN_SAFETY_RULES}

    @app.post("/api/safety/simulate")
    async def simulate_safety(req: SafetySimulateRequest):
        if req.quantity <= 0:
            raise HTTPException(status_code=422, detail="quantity must be greater than 0")
        if req.price <= 0:
            raise HTTPException(status_code=422, detail="price must be greater than 0")
        if req.action.upper() not in ("BUY", "SELL"):
            raise HTTPException(status_code=422, detail="action must be BUY or SELL")

        rejections = []
        warnings = []
        order_value = req.quantity * req.price

        # Check maximum single order value
        if order_value > FROZEN_SAFETY_RULES["max_order_value_inr"]:
            rejections.append(
                f"Order value ₹{order_value:,.2f} exceeds ceiling ₹{FROZEN_SAFETY_RULES['max_order_value_inr']:,.2f}"
            )

        # Check position sizing percentage vs capital (1,000,000 baseline)
        position_pct = order_value / 1000000.0
        if position_pct > FROZEN_SAFETY_RULES["max_position_pct"]:
            rejections.append(
                f"Order allocation {position_pct*100:.1f}% exceeds max {FROZEN_SAFETY_RULES['max_position_pct']*100:.1f}%"
            )

        # Check stop loss constraints
        if FROZEN_SAFETY_RULES["require_stop_loss"]:
            if req.stop_loss is None or req.stop_loss <= 0:
                rejections.append("Mandatory stop-loss is missing or invalid")
            elif req.action.upper() == "BUY":
                if req.stop_loss >= req.price:
                    rejections.append(f"Stop-loss ₹{req.stop_loss} cannot be >= entry price ₹{req.price}")
                else:
                    sl_pct = (req.price - req.stop_loss) / req.price
                    if sl_pct < FROZEN_SAFETY_RULES["min_stop_loss_pct"]:
                        rejections.append(
                            f"Stop-loss distance {sl_pct*100:.2f}% is below minimum {FROZEN_SAFETY_RULES['min_stop_loss_pct']*100:.1f}%"
                        )

        passed = len(rejections) == 0
        return {
            "passed": passed,
            "rejections": rejections,
            "warnings": warnings,
            "risk_pct": round(position_pct * 100, 2),
            "simulated_order_value": order_value,
            "max_allowed_quantity": int((1000000.0 * FROZEN_SAFETY_RULES["max_position_pct"]) / req.price),
        }

    @app.get("/api/safety/status")
    async def get_safety_status():
        return {
            "circuit_breaker_tripped": False,
            "daily_drawdown_pct": 0.45,
            "daily_drawdown_limit_pct": 3.0,
            "kill_switch_active": False,
            "open_positions_count": 1,
            "max_allowed_positions": 5,
            "orders_last_minute": 2,
            "max_orders_per_minute": 20,
            "market_hours_open": True,
        }

    # ── 8. SYSTEM ROUTER ────────────────────────────────────────────────────

    @app.get("/api/system/config")
    async def get_system_config():
        return {
            "environment": "development",
            "trading_mode": "paper",
            "asset_class": "equity",
            "scanner_interval_seconds": 30,
            "initial_capital": 1000000.0,
            "secrets_status": {
                "google_api_key": "configured (masked: AIzaSy...****)",
                "anthropic_api_key": "configured (masked: sk-ant-...****)",
                "perplexity_api_key": "configured (masked: pplx-...****)",
                "xai_api_key": "configured (masked: xai-...****)",
                "supabase_url": "configured (masked: https://...****)",
                "indstocks_token": "configured (masked: ind_...****)",
            },
        }

    @app.get("/api/system/models")
    async def get_system_models():
        return {
            "mappings": {
                "analyst_team": {"provider": "google", "model": "gemini-2.0-flash"},
                "market_scanner": {"provider": "google", "model": "gemini-2.0-flash"},
                "news_research": {"provider": "perplexity", "model": "perplexity-sonar"},
                "social_research": {"provider": "xai", "model": "xai-grok"},
                "research_judge": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
                "risk_judge": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
                "chat_assistant": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
            }
        }

    @app.get("/api/system/strategies")
    async def get_system_strategies():
        return {"active": strategies_db[0], "history": strategies_db}

    @app.get("/api/system/healing")
    async def get_healing_events(limit: int = 50, component: Optional[str] = None):
        events = list(healing_events_db)
        if component:
            events = [e for e in events if e["component"] == component]
        return {"events": events[:limit], "total": len(events), "unresolved_count": 0}

    @app.post("/api/system/healing/log")
    async def log_healing_event(req: HealingLogRequest):
        new_event = {
            "id": f"heal_{str(uuid4())[:8]}",
            "component": req.component,
            "event_type": req.event_type,
            "description": req.description,
            "action_taken": req.action_taken,
            "resolved": req.resolved,
            "metadata": req.metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        healing_events_db.append(new_event)
        return {"status": "logged", "event": new_event}

    # ── 9. CHAT ASSISTANT ROUTER ────────────────────────────────────────────

    @app.post("/api/chat/message")
    async def chat_message(req: ChatMessageRequest):
        msg = req.message.strip()
        if not msg:
            raise HTTPException(status_code=422, detail="Message cannot be empty")

        sess_id = req.session_id or str(uuid4())
        if sess_id not in chat_sessions:
            chat_sessions[sess_id] = []

        history = chat_sessions[sess_id]
        history.append({"role": "user", "content": msg})

        # Simulate intelligent assistant responses with tool calls
        tool_calls = []
        if "portfolio" in msg.lower() or "positions" in msg.lower():
            tool_calls.append({
                "tool": "get_portfolio",
                "args": {},
                "result": "Portfolio: Total Value ₹10,45,250 | Cash ₹4,25,000 | Open Positions: 1 (INFY)",
            })
            assistant_reply = (
                "Your current portfolio value is ₹10,45,250.00 with ₹4,25,000.00 in available cash. "
                "You hold 30 shares of INFY with an unrealized profit of ₹450.00 (+0.82%)."
            )
        elif "analyze" in msg.lower():
            match = re.search(r"analyze\s+([A-Za-z0-9]+)", msg, re.IGNORECASE)
            sym = match.group(1).upper() if match else "RELIANCE"
            tool_calls.append({
                "tool": "analyze_stock",
                "args": {"symbol": sym},
                "result": f"Analysis complete for {sym}: Verdict BUY (Confidence 84%). Stop-loss ₹2790, Target ₹2970.",
            })
            assistant_reply = (
                f"I initiated multi-agent swarm analysis for **{sym}**.\n\n"
                "- **Verdict**: BUY\n- **Confidence**: 84%\n- **Suggested Stop-Loss**: ₹2790\n- **Target**: ₹2970\n"
                "The setup shows technical breakout with positive sentiment alignment."
            )
        elif "safety" in msg.lower():
            tool_calls.append({
                "tool": "check_safety",
                "args": {"symbol": "TCS", "action": "BUY", "quantity": 10, "price": 3800.0},
                "result": "Safety Check: PASSED (Order value ₹38,000 is 3.8% of portfolio).",
            })
            assistant_reply = "Safety simulation passed! Order value ₹38,000 complies with the 15% position limit."
        else:
            assistant_reply = f"I am your Skopaq AI Trading Assistant. How can I assist you with Indian equity trading today?"

        history.append({"role": "assistant", "content": assistant_reply})

        return {
            "message": assistant_reply,
            "session_id": sess_id,
            "tool_calls": tool_calls,
        }

    @app.post("/api/chat/tool")
    async def chat_tool_endpoint(req: ChatToolRequest):
        KNOWN_TOOLS = [
            "get_portfolio",
            "get_quote",
            "check_safety",
            "check_status",
            "compute_position_size",
            "analyze_stock",
            "view_past_trades",
            "recall_memory",
        ]
        if req.tool not in KNOWN_TOOLS:
            raise HTTPException(status_code=400, detail=f"Unknown tool: '{req.tool}'")

        if req.tool == "get_portfolio":
            return {"result": "Portfolio: ₹10,45,250 | Cash: ₹4,25,000"}
        elif req.tool == "check_safety":
            return {"result": "Safety check PASSED: Order within risk envelope"}
        elif req.tool == "get_quote":
            sym = req.args.get("symbol", "RELIANCE")
            return {"result": f"Quote for {sym}: LTP=₹2855.00 (+2.4%)"}
        elif req.tool == "check_status":
            return {"result": "System Status: Paper Mode, Broker INDstocks Connected"}
        elif req.tool == "compute_position_size":
            return {"result": "Calculated position: 25 shares (Risk ₹2500)"}
        elif req.tool == "analyze_stock":
            sym = req.args.get("symbol", "RELIANCE")
            return {"result": f"Analysis complete for {sym}: BUY (84%)"}
        elif req.tool == "view_past_trades":
            return {"result": f"Retrieved {len(trades_db)} recent trades"}
        elif req.tool == "recall_memory":
            return {"result": "Recalled 2 situations from BM25 memory"}

        return {"result": "Tool executed successfully"}

    # ── 10. FRONTEND WEB ROUTES ─────────────────────────────────────────────

    VIEW_ROUTES = [
        ("/", "System Overview Dashboard"),
        ("/portfolio", "Portfolio & Open Positions"),
        ("/scanner", "Market Scanner View"),
        ("/analysis", "Multi-Agent Analysis View"),
        ("/trades", "Trades History"),
        ("/chat", "Interactive AI Trading Chat"),
        ("/analytics", "Performance Analytics"),
        ("/settings", "Settings & System Health"),
    ]

    for route_path, route_title in VIEW_ROUTES:
        def make_handler(title: str):
            async def handler():
                html_content = (
                    f"<!DOCTYPE html><html><head><title>SkopaqTrader - {title}</title></head>"
                    f"<body class='dark bg-gray-950 text-gray-100'><div id='__next'><h1>{title}</h1></div></body></html>"
                )
                return HTMLResponse(content=html_content, status_code=200)
            return handler

        app.add_api_route(
            route_path,
            make_handler(route_title),
            methods=["GET"],
            response_class=HTMLResponse,
            include_in_schema=False,
        )

    return app
