"""Unit tests for novaswarm/api/safety_router.py."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novaswarm.api.safety_router import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_safety_rules(client):
    """GET /api/safety/rules returns mode and frozen rules dictionary."""
    resp = client.get("/api/safety/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data
    assert "rules" in data
    rules = data["rules"]
    assert rules["max_position_pct"] == 0.15
    assert rules["max_daily_loss_pct"] == 0.03
    assert rules["max_open_positions"] == 5
    assert rules["max_order_value_inr"] == 500000.0


def test_simulate_safety_pass(client):
    """Simulating a reasonable position size within limits passes safety check."""
    resp = client.post(
        "/api/safety/simulate",
        json={
            "symbol": "INFY",
            "action": "BUY",
            "quantity": 3,
            "price": 1800.0,
            "stop_loss": 1750.0,
            "confidence": 85,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["rejections"] == []
    assert data["simulated_order_value"] == 5400.0
    assert data["simulated_position_pct"] > 0
    assert data["account_context"]["sector"] == "IT"


def test_simulate_safety_reject_oversized(client):
    """Simulating an order exceeding max capital or single order value is rejected."""
    resp = client.post(
        "/api/safety/simulate",
        json={
            "symbol": "RELIANCE",
            "action": "BUY",
            "quantity": 1000,
            "price": 2800.0,  # 28 Lakhs > 5 Lakh cap
            "stop_loss": 2700.0,
            "confidence": 75,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert len(data["rejections"]) > 0
    assert any("order value" in r.lower() or "position size" in r.lower() or "funds" in r.lower() for r in data["rejections"])


def test_get_safety_status(client):
    """GET /api/safety/status returns live risk and circuit breaker state."""
    resp = client.get("/api/safety/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "circuit_breaker_tripped" in data
    assert "day_pnl" in data
    assert "day_loss_limit_inr" in data
    assert "market_hours" in data
    assert "ist_time" in data["market_hours"]
    assert "rate_limits" in data
