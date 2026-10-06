"""End-to-end unit verification for all expanded endpoints mounted directly on server.app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skopaq.api.server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_existing_endpoints_preserved(client):
    """Verify pre-existing endpoints continue to respond properly."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert "broker" in resp.json()

    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    assert "total_value" in resp.json()

    resp = client.get("/api/scanner/status")
    assert resp.status_code == 200


def test_trades_endpoints_on_server(client):
    """Verify /api/trades endpoints on server.app."""
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    data = resp.json()
    assert "trades" in data
    assert "total" in data

    resp = client.get("/api/trades/summary/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "win_rate" in data
    assert "total_trades" in data


def test_analysis_endpoints_on_server(client):
    """Verify /api/analysis lifecycle on server.app."""
    start_resp = client.post(
        "/api/analysis",
        json={"symbol": "INFY", "urgency": "medium"},
    )
    assert start_resp.status_code == 202
    job_id = start_resp.json()["job_id"]

    status_resp = client.get(f"/api/analysis/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["symbol"] == "INFY"

    with client.stream("GET", f"/api/analysis/{job_id}/stream") as stream_resp:
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")
        lines = []
        for line in stream_resp.iter_lines():
            if line:
                lines.append(line)
                if len(lines) >= 3:
                    break
        assert len(lines) >= 1


def test_memory_endpoints_on_server(client):
    """Verify /api/memory endpoints on server.app."""
    resp = client.get("/api/memory/roles")
    assert resp.status_code == 200
    assert len(resp.json()["roles"]) == 5

    resp = client.get("/api/memory/role/bull_memory")
    assert resp.status_code == 200
    assert "entries" in resp.json()

    resp = client.post(
        "/api/memory/query",
        json={"role": "bull_memory", "query": "breakout", "top_k": 3},
    )
    assert resp.status_code == 200
    assert "results" in resp.json()

    resp = client.get("/api/memory/reflections")
    assert resp.status_code == 200
    assert "reflections" in resp.json()


def test_performance_endpoints_on_server(client):
    """Verify /api/performance endpoints on server.app."""
    resp = client.get("/api/performance/metrics")
    assert resp.status_code == 200
    assert "portfolio_value" in resp.json()

    resp = client.get("/api/performance/daily-snapshots")
    assert resp.status_code == 200
    assert "snapshots" in resp.json()

    resp = client.get("/api/performance/models")
    assert resp.status_code == 200
    assert "models" in resp.json()

    resp = client.get("/api/performance/learning")
    assert resp.status_code == 200
    assert "active_version" in resp.json()


def test_safety_endpoints_on_server(client):
    """Verify /api/safety endpoints on server.app."""
    resp = client.get("/api/safety/rules")
    assert resp.status_code == 200
    assert "rules" in resp.json()

    resp = client.post(
        "/api/safety/simulate",
        json={"symbol": "TCS", "action": "BUY", "quantity": 2, "price": 3600.0, "stop_loss": 3500.0},
    )
    assert resp.status_code == 200
    assert "passed" in resp.json()

    resp = client.get("/api/safety/status")
    assert resp.status_code == 200
    assert "circuit_breaker_tripped" in resp.json()


def test_system_endpoints_on_server(client):
    """Verify /api/system endpoints on server.app."""
    resp = client.get("/api/system/config")
    assert resp.status_code == 200
    assert "trading_mode" in resp.json()

    resp = client.get("/api/system/models")
    assert resp.status_code == 200
    assert "roles" in resp.json()

    resp = client.get("/api/system/strategies")
    assert resp.status_code == 200
    assert "dna_yaml" in resp.json()

    resp = client.get("/api/system/healing")
    assert resp.status_code == 200
    assert "events" in resp.json()

    resp = client.post(
        "/api/system/healing/log",
        json={"component": "test", "event_type": "check", "resolved": True},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in ("success", "acknowledged_in_memory")
