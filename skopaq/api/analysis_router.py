"""FastAPI router for asynchronous multi-agent stock analysis and SSE progress streaming."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from skopaq.api.analysis_models import (
    AnalysisJobStatus,
    AnalysisStartRequest,
    AnalysisStartResponse,
)
from skopaq.api.analysis_manager import (
    AnalysisJobManager,
    execute_analysis_worker,
)
from skopaq.config import SkopaqConfig
from skopaq.data.symbol_validator import validate_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/validate", response_model=dict)
async def validate_analysis_symbol(
    symbol: str = Query(..., min_length=1, description="Stock or crypto symbol to validate"),
    asset_class: str = Query("equity", description="equity or crypto"),
) -> dict:
    """Validate a trading symbol for analysis before job initiation."""
    val_res = await validate_symbol(symbol=symbol, asset_class=asset_class)
    return val_res.model_dump()


@router.post("", response_model=AnalysisStartResponse, status_code=202)
async def start_analysis(req: AnalysisStartRequest) -> AnalysisStartResponse:
    """Trigger background multi-agent stock analysis and return a trackable job ID."""
    config = SkopaqConfig()
    symbol = req.symbol.strip().upper()
    trade_date = req.trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    asset_class = req.asset_class or config.asset_class

    # Validate symbol before accepting job
    val_res = await validate_symbol(symbol=symbol, asset_class=asset_class)
    if not val_res.valid:
        raise HTTPException(
            status_code=422,
            detail=(
                val_res.error or f"Invalid symbol '{symbol}'. Ticker could not be verified on {asset_class} exchanges."
            ),
        )

    mgr = AnalysisJobManager.get_instance()
    job = mgr.create_job(
        symbol=val_res.symbol,
        trade_date=trade_date,
        asset_class=asset_class,
        urgency=req.urgency or "medium",
        lookback_days=req.lookback_days or 30,
        selected_analysts=req.selected_analysts,
    )

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        mgr._executor,
        execute_analysis_worker,
        job,
        loop,
    )

    return AnalysisStartResponse(
        job_id=job.job_id,
        symbol=job.symbol,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("", response_model=dict)
async def list_analyses(limit: int = Query(20, ge=1, le=100)) -> dict:
    """List recent analysis jobs."""
    mgr = AnalysisJobManager.get_instance()
    jobs = mgr.list_jobs(limit=limit)
    return {
        "jobs": [j.to_status().model_dump() for j in jobs],
        "total": len(jobs),
    }


@router.get("/{job_id}", response_model=AnalysisJobStatus)
async def get_analysis_status(job_id: str) -> AnalysisJobStatus:
    """Fetch the current execution state, intermediate reports, and decision card."""
    mgr = AnalysisJobManager.get_instance()
    job = mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")
    return job.to_status()


@router.get("/{job_id}/stream")
async def stream_analysis(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming endpoint for live agent progress and token generation."""
    mgr = AnalysisJobManager.get_instance()
    job = mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        client_queue: asyncio.Queue = asyncio.Queue()
        sub_tuple = (client_queue, asyncio.get_running_loop())
        job.subscribers.append(sub_tuple)

        try:
            # 1. Replay historical buffered events for late joiners or reconnected clients
            for past_event in list(job.events):
                yield f"event: {past_event['event']}\ndata: {json.dumps(past_event['data'], default=str)}\n\n"

            # If already finished, terminate stream cleanly
            if job.status in ("completed", "failed") and client_queue.empty():
                return

            # 2. Stream live events with 15s keep-alive heartbeat comments
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=15.0)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"
                    if event.get("event") in ("job_completed", "job_failed"):
                        break
                except asyncio.TimeoutError:
                    if job.status in ("completed", "failed"):
                        break
                    yield ": keepalive\n\n"
        finally:
            if sub_tuple in job.subscribers:
                job.subscribers.remove(sub_tuple)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
