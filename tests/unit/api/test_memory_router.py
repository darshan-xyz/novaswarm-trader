"""Unit tests for skopaq/api/memory_router.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skopaq.api.memory_router import router
from skopaq.db.models import AgentMemoryRecord


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_roles_offline(client):
    """When Supabase is offline, list_roles returns the 5 canonical roles with 0 counts."""
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/memory/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["roles"]) == 5
        assert data["total_memories"] == 0
        role_names = [r["role"] for r in data["roles"]]
        assert "bull_memory" in role_names
        assert "bear_memory" in role_names
        assert "trader_memory" in role_names
        assert "invest_judge_memory" in role_names
        assert "risk_manager_memory" in role_names


def test_list_roles_with_data(client):
    """When Supabase has records, list_roles populates document counts."""
    mock_record = AgentMemoryRecord(
        role="bull_memory",
        documents=["Sit 1", "Sit 2", "Sit 3"],
        recommendations=["Rec 1", "Rec 2", "Rec 3"],
        updated_at=datetime.now(timezone.utc),
    )
    mock_client = MagicMock()
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.memory_router.MemoryRepository.get_all_roles", return_value=[mock_record]):
        resp = client.get("/api/memory/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_memories"] == 3
        bull = next(r for r in data["roles"] if r["role"] == "bull_memory")
        assert bull["count"] == 3
        assert bull["updated_at"] is not None


def test_get_role_memories_offline(client):
    """GET /api/memory/role/{role} returns empty list when offline."""
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/memory/role/bull_memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "bull_memory"
        assert data["entries"] == []
        assert data["count"] == 0


def test_get_role_memories_with_data(client):
    """GET /api/memory/role/{role} returns situation-recommendation pairs."""
    mock_record = AgentMemoryRecord(
        role="risk_manager_memory",
        documents=["VIX spiked above 25 with heavy intraday swings."],
        recommendations=["Cut position size in half and widen ATR stops."],
    )
    mock_client = MagicMock()
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_record):
        resp = client.get("/api/memory/role/risk_manager_memory?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "VIX spiked" in data["entries"][0]["situation"]
        assert "Cut position" in data["entries"][0]["recommendation"]


def test_query_memory_bm25(client):
    """POST /api/memory/query runs BM25 matching and returns top ranked results."""
    mock_record = AgentMemoryRecord(
        role="trader_memory",
        documents=[
            "Breakout failure on gap-up opening without follow-through volume.",
            "Consolidation near 50-day moving average followed by high volume surge.",
            "Earnings report beat expectations but guidance was weak.",
        ],
        recommendations=[
            "Wait for 15-minute confirmation candle before entering gap-ups.",
            "Enter on pullback test of moving average support.",
            "Avoid holding long options through corporate earnings calls.",
        ],
    )
    mock_client = MagicMock()
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_record):
        resp = client.post(
            "/api/memory/query",
            json={
                "role": "trader_memory",
                "query": "breakout gap-up volume",
                "top_k": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "trader_memory"
        assert len(data["results"]) >= 1
        assert "gap-up" in data["results"][0]["matched_situation"]
        assert data["results"][0]["similarity_score"] > 0


def test_reflections_offline(client):
    """GET /api/memory/reflections returns empty list when offline."""
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/memory/reflections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reflections"] == []
        assert data["count"] == 0


def test_reflections_with_data(client):
    """GET /api/memory/reflections retrieves reflection records with optional symbol filter."""
    mock_reflections = [
        {"symbol": "RELIANCE", "reflection": "Good trend follow", "pnl": 1200.0, "pnl_pct": 2.5, "trade_date": "2026-09-22"},
        {"symbol": "INFY", "reflection": "Stop hit on tech selloff", "pnl": -800.0, "pnl_pct": -1.8, "trade_date": "2026-09-22"},
    ]
    mock_client = MagicMock()
    with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.memory_router.load_recent_lessons", return_value=mock_reflections):
        resp = client.get("/api/memory/reflections?symbol=RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["reflections"][0]["symbol"] == "RELIANCE"
