"""Adversarial stress and boundary correctness test suite for SkopaqTrader.

Milestone 6: Empirical verification of backend robustness, boundary validation,
concurrency limits, SSE stream durability, and pre-trade safety constraints.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import json
import time
from typing import Any, Dict, List, Tuple
import pytest

from fastapi.testclient import TestClient
from skopaq.api.server import app
from skopaq.api.analysis_manager import AnalysisJobManager, AnalysisJob
from skopaq.broker.paper_engine import PaperEngine
from skopaq.execution.safety_checker import SafetyChecker
from skopaq.constants import PAPER_SAFETY_RULES, SAFETY_RULES


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. ANALYSIS ROUTER: BOUNDARY VALIDATION & INJECTION TESTS
# ==============================================================================

class TestAnalysisBoundaries:
    """Boundary conditions and adversarial inputs on /api/analysis."""

    def test_invalid_symbol_special_characters(self, client):
        """Adversarial input: symbol with invalid punctuation/special characters."""
        resp = client.post("/api/analysis", json={"symbol": "INVALID$$%%^^"})
        # In an enterprise API, malformed tickers should be rejected with 422
        return resp.status_code, resp.json()

    def test_invalid_symbol_sql_injection(self, client):
        """Adversarial input: symbol with SQL injection payload."""
        resp = client.post("/api/analysis", json={"symbol": "TCS'; DROP TABLE trades;--"})
        return resp.status_code, resp.json()

    def test_invalid_symbol_xss_html(self, client):
        """Adversarial input: symbol with HTML/XSS payload."""
        resp = client.post("/api/analysis", json={"symbol": "<script>alert(1)</script>"})
        return resp.status_code, resp.json()

    def test_invalid_symbol_empty_string(self, client):
        """Boundary: empty symbol."""
        resp = client.post("/api/analysis", json={"symbol": ""})
        assert resp.status_code == 422, f"Expected 422 for empty symbol, got {resp.status_code}"

    def test_lookback_days_negative(self, client):
        """Boundary: negative lookback days."""
        resp = client.post("/api/analysis", json={"symbol": "RELIANCE", "lookback_days": -5})
        return resp.status_code, resp.json()

    def test_lookback_days_zero(self, client):
        """Boundary: 0 lookback days."""
        resp = client.post("/api/analysis", json={"symbol": "RELIANCE", "lookback_days": 0})
        return resp.status_code, resp.json()

    def test_lookback_days_excessive(self, client):
        """Boundary: >365 lookback days."""
        resp = client.post("/api/analysis", json={"symbol": "RELIANCE", "lookback_days": 1000})
        return resp.status_code, resp.json()


# ==============================================================================
# 2. ANALYSIS ROUTER: CONCURRENCY & STREAM CONNECT/DISCONNECT STRESS
# ==============================================================================

class TestAnalysisConcurrencyAndStress:
    """Stress tests for concurrent jobs and rapid SSE stream connects/disconnects."""

    def test_concurrent_job_creation(self, client):
        """Stress: spawn 30 concurrent analysis requests."""
        symbols = [f"SYM{i}" for i in range(30)]
        results = []

        def submit_job(sym):
            return client.post("/api/analysis", json={"symbol": sym})

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(submit_job, s) for s in symbols]
            for f in as_completed(futures):
                results.append(f.result())

        statuses = [r.status_code for r in results]
        assert all(s == 202 for s in statuses), f"Non-202 status codes in concurrent creation: {statuses}"
        job_ids = [r.json()["job_id"] for r in results]
        assert len(set(job_ids)) == 30, "Job IDs were not unique under concurrency!"

    def test_rapid_stream_connect_disconnect_stress(self, client):
        """Stress: 40 rapid connect and immediate disconnect cycles on active job."""
        # Create a job
        resp = client.post("/api/analysis", json={"symbol": "INFY"})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        mgr = AnalysisJobManager.get_instance()
        job = mgr.get_job(job_id)
        assert job is not None

        # Rapidly connect and abort without consuming the full stream
        def connect_and_abort():
            try:
                with client.stream("GET", f"/api/analysis/{job_id}/stream") as stream_resp:
                    # Read just 1 line or chunk and immediately close
                    for chunk in stream_resp.iter_lines():
                        if chunk:
                            break
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(connect_and_abort) for _ in range(40)]
            for f in as_completed(futures):
                f.result()

        # Check job health and that subscribers list cleaned up properly
        time.sleep(0.5)
        # Subscribers list should not leak unbounded dead queues
        active_subscribers = len(job.subscribers)
        return {"job_id": job_id, "active_subscribers": active_subscribers, "events_count": len(job.events)}


# ==============================================================================
# 3. PRE-TRADE SAFETY SIMULATION: EXTREME BOUNDARY TESTING
# ==============================================================================

class TestSafetySimulationBoundaries:
    """Empirical verification of safety simulation against risk rules."""

    def test_negative_price_rejected_by_schema(self, client):
        """Boundary: negative price returns 422."""
        resp = client.post(
            "/api/safety/simulate",
            json={"symbol": "RELIANCE", "action": "BUY", "quantity": 10, "price": -2800.0, "stop_loss": 2700.0},
        )
        assert resp.status_code == 422, f"Negative price returned {resp.status_code}, expected 422"

    def test_zero_price_rejected_by_schema(self, client):
        """Boundary: zero price returns 422."""
        resp = client.post(
            "/api/safety/simulate",
            json={"symbol": "RELIANCE", "action": "BUY", "quantity": 10, "price": 0.0, "stop_loss": 2700.0},
        )
        assert resp.status_code == 422, f"Zero price returned {resp.status_code}, expected 422"

    def test_zero_quantity_rejected_by_schema(self, client):
        """Boundary: zero quantity returns 422."""
        resp = client.post(
            "/api/safety/simulate",
            json={"symbol": "RELIANCE", "action": "BUY", "quantity": 0, "price": 2800.0, "stop_loss": 2700.0},
        )
        assert resp.status_code == 422, f"Zero quantity returned {resp.status_code}, expected 422"

    def test_huge_quantity_exceeding_capital_rejected(self, client):
        """Extreme value: huge quantity 1,000,000 shares."""
        resp = client.post(
            "/api/safety/simulate",
            json={"symbol": "RELIANCE", "action": "BUY", "quantity": 1_000_000, "price": 2800.0, "stop_loss": 2700.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is False, "Oversized order unexpectedly passed safety check!"
        assert len(data["rejections"]) > 0

    def test_inverted_stop_loss_buy_higher_than_price(self, client):
        """Vulnerability probe: BUY order with stop_loss HIGHER than entry price."""
        resp = client.post(
            "/api/safety/simulate",
            json={
                "symbol": "INFY",
                "action": "BUY",
                "quantity": 2,
                "price": 1800.0,
                "stop_loss": 1850.0,  # INVERTED: Higher than entry price!
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        return data

    def test_inverted_stop_loss_sell_lower_than_price(self, client):
        """Vulnerability probe: SELL order with stop_loss LOWER than entry price."""
        resp = client.post(
            "/api/safety/simulate",
            json={
                "symbol": "INFY",
                "action": "SELL",
                "quantity": 2,
                "price": 1800.0,
                "stop_loss": 1750.0,  # INVERTED for short: Lower than entry price!
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        return data

    def test_tight_stop_loss_below_min_pct(self, client):
        """Vulnerability probe: stop loss distance 0.05% < 2% minimum threshold."""
        resp = client.post(
            "/api/safety/simulate",
            json={
                "symbol": "INFY",
                "action": "BUY",
                "quantity": 2,
                "price": 1800.0,
                "stop_loss": 1799.0,  # 0.05% distance
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        return data


# ==============================================================================
# 4. SSE STREAMING DURABILITY & LATE-JOINER REPLAY BUFFER
# ==============================================================================

class TestSSEStreamingDurability:
    """Durability, event ordering, late-joiner replay, and concurrency race probes."""

    def test_late_joiner_receives_complete_buffer_on_completed_job(self, client):
        """Verify late joiner receives full sequence of events on finished job."""
        # 1. Trigger job
        start_resp = client.post("/api/analysis", json={"symbol": "TCS"})
        assert start_resp.status_code == 202
        job_id = start_resp.json()["job_id"]

        # 2. Wait until job completes
        for _ in range(50):
            status_resp = client.get(f"/api/analysis/{job_id}")
            if status_resp.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)

        job_state = client.get(f"/api/analysis/{job_id}").json()
        assert job_state["status"] == "completed"

        # 3. Connect late joiner to SSE stream
        received_events = []
        with client.stream("GET", f"/api/analysis/{job_id}/stream") as stream:
            current_event = None
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    current_event = line.replace("event: ", "").strip()
                elif line.startswith("data: ") and current_event:
                    data = json.loads(line.replace("data: ", "").strip())
                    received_events.append({"event": current_event, "data": data})
                    current_event = None

        event_names = [e["event"] for e in received_events]
        assert "job_started" in event_names, "Late joiner missed job_started"
        assert "agent_status" in event_names, "Late joiner missed agent_status"
        assert "decision_card" in event_names, "Late joiner missed decision_card"
        assert "job_completed" in event_names, "Late joiner missed job_completed"
        assert event_names[0] == "job_started"
        assert event_names[-1] == "job_completed"

    def test_sse_replay_race_condition_empirical_check(self):
        """Test for event duplication race condition in AnalysisJob event generator."""
        async def run_race_probe():
            job = AnalysisJob("probe-job-1", "RELIANCE", "2026-09-23", "equity")
            job.emit_event("e1", {"msg": "first"})

            # Client connects and subscribes
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            sub_tuple = (queue, loop)
            job.subscribers.append(sub_tuple)

            # Background worker thread emits e2 while subscriber is registered
            job.emit_event("e2", {"msg": "second"})

            # Allow event loop to process call_soon_threadsafe
            await asyncio.sleep(0.001)

            # Replay simulation as implemented in analysis_router.py
            delivered = []
            for ev in list(job.events):
                delivered.append(ev["event"])

            while not queue.empty():
                q_ev = queue.get_nowait()
                delivered.append(q_ev["event"])

            return delivered

        events = asyncio.run(run_race_probe())
        has_duplicates = len(events) != len(set(events))
        return {"events": events, "has_duplicates": has_duplicates}
