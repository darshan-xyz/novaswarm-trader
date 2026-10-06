"""Unit tests for novaswarm/api/system_router.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novaswarm.api.system_router import router
from novaswarm.db.models import HealingEventRecord, StrategyVersionRecord


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_system_config(client):
    """GET /api/system/config returns sanitized parameters and masked service flags."""
    resp = client.get("/api/system/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "trading_mode" in data
    assert "scanner" in data
    assert "services" in data
    # Ensure no raw secrets leaked
    assert isinstance(data["services"]["google_ai"], bool)
    assert isinstance(data["services"]["supabase"], bool)
    assert "api_key" not in data


def test_get_model_mappings(client):
    """GET /api/system/models returns role-to-model tiering configurations."""
    resp = client.get("/api/system/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert data["total_roles"] >= 10
    role_keys = [r["role"] for r in data["roles"]]
    assert "market_analyst" in role_keys
    assert "research_manager" in role_keys
    assert "trader" in role_keys
    assert "risk_manager" in role_keys


def test_get_strategies_fallback(client):
    """GET /api/system/strategies returns default Strategy DNA when DB has no versions."""
    with patch("novaswarm.api.system_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/system/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "dna_yaml" in data
        assert "NovaSwarmMultiAgentTrendBreakout" in data["dna_yaml"]


def test_get_healing_events_offline(client):
    """GET /api/system/healing returns empty list when offline."""
    with patch("novaswarm.api.system_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/system/healing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["unresolved_count"] == 0


def test_log_healing_event(client):
    """POST /api/system/healing/log records a self-healing event."""
    resp = client.post(
        "/api/system/healing/log",
        json={
            "component": "websocket",
            "event_type": "reconnect",
            "description": "INDstocks price channel auto-reconnected",
            "action_taken": "Backoff retry",
            "resolved": True,
            "metadata": {"retry_count": 1},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("success", "acknowledged_in_memory")
    assert data["event"]["component"] == "websocket"
    assert data["event"]["event_type"] == "reconnect"
