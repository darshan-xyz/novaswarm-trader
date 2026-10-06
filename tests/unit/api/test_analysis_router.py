"""Unit tests for skopaq/api/analysis_router.py and analysis_manager.py."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skopaq.api.analysis_manager import (
    AnalysisJob,
    AnalysisJobManager,
    execute_analysis_worker,
)
from skopaq.api.analysis_models import DecisionCard
from skopaq.api.analysis_router import router


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset the singleton instance between tests."""
    AnalysisJobManager.reset_instance()
    yield
    AnalysisJobManager.reset_instance()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_start_analysis_endpoint(client):
    """POST /api/analysis returns 202 Accepted with a valid job ID."""
    resp = client.post(
        "/api/analysis",
        json={
            "symbol": "RELIANCE",
            "urgency": "high",
            "lookback_days": 45,
        },
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["symbol"] == "RELIANCE"
    assert data["status"] in ("pending", "running", "completed")


def test_get_analysis_not_found(client):
    """GET /api/analysis/{job_id} returns 404 for unknown job IDs."""
    resp = client.get("/api/analysis/nonexistent-job-id")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_analysis_status_success(client):
    """GET /api/analysis/{job_id} returns status and completed reports."""
    mgr = AnalysisJobManager.get_instance()
    job = mgr.create_job("TCS", "2026-09-23", "equity")
    job.status = "completed"
    job.agent_statuses["market_analyst"] = "completed"
    job.reports["market_analyst_report"] = "Bullish structure confirmed."
    job.decision = DecisionCard(
        symbol="TCS",
        action="BUY",
        confidence=82,
        entry_price=3500.0,
        stop_loss=3420.0,
        target=3660.0,
        position_size=15,
        reasoning="Multi-model consensus positive.",
    )

    resp = client.get(f"/api/analysis/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job.job_id
    assert data["symbol"] == "TCS"
    assert data["status"] == "completed"
    assert data["agent_statuses"]["market_analyst"] == "completed"
    assert data["reports"]["market_analyst_report"] == "Bullish structure confirmed."
    assert data["decision"]["action"] == "BUY"
    assert data["decision"]["confidence"] == 82


def test_list_analyses_endpoint(client):
    """GET /api/analysis returns recent job summaries."""
    mgr = AnalysisJobManager.get_instance()
    mgr.create_job("INFY", "2026-09-23", "equity")
    mgr.create_job("SBIN", "2026-09-23", "equity")

    resp = client.get("/api/analysis?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["jobs"]) >= 2
    symbols = [j["symbol"] for j in data["jobs"]]
    assert "INFY" in symbols
    assert "SBIN" in symbols


def test_execute_analysis_worker_full_pipeline():
    """Worker runs full multi-agent pipeline, emits expected events, and populates decision card."""
    loop = asyncio.new_event_loop()
    mgr = AnalysisJobManager.get_instance()
    job = mgr.create_job("HDFCBANK", "2026-09-23", "equity")

    # Run synchronously with 0 sleep for instant test execution
    execute_analysis_worker(job, loop=loop, sleep_interval=0.0)

    assert job.status == "completed"
    assert job.decision is not None
    assert job.decision.symbol == "HDFCBANK"
    assert job.decision.action == "BUY"
    assert job.decision.confidence > 0
    assert job.decision.position_size is not None
    assert job.decision.position_size >= 1

    event_types = [e["event"] for e in job.events]
    assert "job_started" in event_types
    assert "agent_status" in event_types
    assert "tool_call" in event_types
    assert "agent_chunk" in event_types
    assert "agent_report" in event_types
    assert "decision_card" in event_types
    assert "job_completed" in event_types

    loop.close()


def test_stream_analysis_replay(client):
    """GET /api/analysis/{job_id}/stream replays past events from buffer for late joiners."""
    mgr = AnalysisJobManager.get_instance()
    job = mgr.create_job("WIPRO", "2026-09-23", "equity")
    job.status = "completed"

    dummy_loop = asyncio.new_event_loop()
    job.emit_event("job_started", {"job_id": job.job_id, "symbol": "WIPRO"}, loop=dummy_loop)
    job.emit_event("agent_status", {"agent_id": "market_analyst", "status": "completed"}, loop=dummy_loop)
    job.emit_event("job_completed", {"job_id": job.job_id, "final_verdict": "BUY"}, loop=dummy_loop)
    dummy_loop.close()

    resp = client.get(f"/api/analysis/{job.job_id}/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    content = resp.text
    assert "event: job_started" in content
    assert "event: agent_status" in content
    assert "event: job_completed" in content
    assert "WIPRO" in content


def test_stream_analysis_not_found(client):
    """Streaming unknown job returns 404."""
    resp = client.get("/api/analysis/invalid-id/stream")
    assert resp.status_code == 404
