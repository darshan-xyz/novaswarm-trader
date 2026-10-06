"""Tier 1 Feature Coverage: Multi-Agent Analysis Background Runner & SSE Stream.

Covers:
- Triggering background analysis job (POST /api/analysis) -> 202 Accepted
- Polling job status (GET /api/analysis/{job_id})
- SSE stream initial job_started and agent_status events
- SSE stream agent reports and real-time chunks
- SSE stream final decision_card generation
- SSE stream terminal job_completed and keepalive heartbeat comments
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_start_analysis_job_success(client: E2EClient):
    """Verify POST /api/analysis queues background job and returns 202 Accepted with job_id."""
    resp = client.start_analysis(symbol="RELIANCE", urgency="high", lookback_days=30)
    assert resp.status_code in (200, 202), f"Expected 202/200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert "job_id" in data
    assert data["symbol"] == "RELIANCE"
    assert data["status"] in ("pending", "running", "completed")
    assert "created_at" in data


def test_get_analysis_job_status(client: E2EClient):
    """Verify GET /api/analysis/{job_id} retrieves current job state and reports snapshot."""
    start_resp = client.start_analysis(symbol="TCS")
    job_id = start_resp.json()["job_id"]

    resp = client.get_analysis_status(job_id)
    assert resp.status_code == 200
    status_data = resp.json()

    assert status_data["job_id"] == job_id
    assert status_data["symbol"] == "TCS"
    assert "agent_statuses" in status_data
    assert "reports" in status_data


def test_stream_analysis_sse_job_started(client: E2EClient):
    """Verify GET /api/analysis/{job_id}/stream emits 'job_started' as first event."""
    start_resp = client.start_analysis(symbol="INFY")
    job_id = start_resp.json()["job_id"]

    events = client.stream_analysis(job_id, max_events=10)
    assert len(events) >= 1, "Expected at least 1 SSE event"

    event_types = [e["event"] for e in events]
    assert "job_started" in event_types, f"job_started event missing from stream: {event_types}"

    job_started_ev = next(e for e in events if e["event"] == "job_started")
    assert job_started_ev["data"]["symbol"] == "INFY"
    assert job_started_ev["data"]["job_id"] == job_id


def test_stream_analysis_sse_reports_and_chunks(client: E2EClient):
    """Verify SSE stream emits agent reports and token chunks."""
    start_resp = client.start_analysis(symbol="HDFCBANK")
    job_id = start_resp.json()["job_id"]

    events = client.stream_analysis(job_id, max_events=20)
    event_types = [e["event"] for e in events]

    assert "agent_report" in event_types, f"agent_report missing: {event_types}"
    assert "agent_chunk" in event_types, f"agent_chunk missing: {event_types}"

    report_ev = next(e for e in events if e["event"] == "agent_report")
    assert "report_markdown" in report_ev["data"]
    assert len(report_ev["data"]["report_markdown"]) > 0


def test_stream_analysis_sse_decision_card(client: E2EClient):
    """Verify SSE stream emits final decision_card with verdict, confidence, and levels."""
    start_resp = client.start_analysis(symbol="TATAMOTORS")
    job_id = start_resp.json()["job_id"]

    events = client.stream_analysis(job_id, max_events=20)
    event_types = [e["event"] for e in events]

    assert "decision_card" in event_types, f"decision_card missing: {event_types}"
    card_ev = next(e for e in events if e["event"] == "decision_card")
    card = card_ev["data"]

    assert card["verdict"] in ("BUY", "SELL", "HOLD")
    assert 0 <= card["confidence"] <= 100
    assert card["entry_price"] > 0
    assert card["stop_loss"] > 0
    assert card["target"] > 0
    assert card["risk_reward_ratio"] > 0


def test_stream_analysis_sse_job_completed_and_heartbeat(client: E2EClient):
    """Verify SSE stream emits job_completed terminal event and keepalive heartbeat."""
    start_resp = client.start_analysis(symbol="BAJFINANCE")
    job_id = start_resp.json()["job_id"]

    events = client.stream_analysis(job_id, max_events=30)
    event_types = [e["event"] for e in events]

    assert "job_completed" in event_types, f"job_completed missing: {event_types}"
    completed_ev = next(e for e in events if e["event"] == "job_completed")
    assert completed_ev["data"]["job_id"] == job_id
    assert completed_ev["data"]["duration_seconds"] > 0

    # Verify keepalive comment
    assert any(e["event"] == "comment" for e in events), "Keepalive comment (: heartbeat) missing"
