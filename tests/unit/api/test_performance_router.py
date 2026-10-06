"""Unit tests for skopaq/api/performance_router.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skopaq.api.performance_router import router
from skopaq.db.models import DailySnapshotRecord


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_performance_metrics(client):
    """GET /api/performance/metrics returns valid portfolio statistics."""
    with patch("skopaq.api.performance_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/performance/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "portfolio_value" in data
        assert "initial_capital" in data
        assert "total_return_pct" in data
        assert "day_pnl" in data
        assert "win_rate" in data
        assert data["mode"] in ("paper", "live")


def test_get_daily_snapshots_fallback(client):
    """When DB has no snapshots, endpoint generates baseline sequence for visual chart."""
    with patch("skopaq.api.performance_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/performance/daily-snapshots?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshots" in data
        assert len(data["snapshots"]) >= 1
        s = data["snapshots"][-1]
        assert "date" in s
        assert "portfolio_value" in s
        assert "cash" in s
        assert "day_pnl" in s


def test_get_daily_snapshots_with_db(client):
    """When snapshots exist in DB, returns records chronologically."""
    mock_snap = DailySnapshotRecord(
        date=date(2026, 9, 22),
        portfolio_value=Decimal("1025000.0"),
        cash=Decimal("500000.0"),
        day_pnl=Decimal("3500.0"),
        total_trades=2,
        winning_trades=2,
        losing_trades=0,
        max_drawdown_pct=Decimal("0.8"),
    )
    mock_client = MagicMock()
    with patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.performance_router.SnapshotRepository.get_range", return_value=[mock_snap]):
        resp = client.get("/api/performance/daily-snapshots?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["snapshots"]) == 1
        assert data["snapshots"][0]["date"] == "2026-09-22"
        assert data["snapshots"][0]["portfolio_value"] == 1025000.0
        assert data["snapshots"][0]["day_pnl"] == 3500.0


def test_get_model_accuracy(client):
    """GET /api/performance/models returns breakdown for primary LLMs."""
    with patch("skopaq.api.performance_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/performance/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) >= 4
        names = [m["model_name"] for m in data["models"]]
        assert "claude-3-5-sonnet" in names
        assert "gemini-2.0-flash" in names
        assert "perplexity-sonar" in names
        assert "xai-grok" in names


def test_get_learning_curve(client):
    """GET /api/performance/learning returns adaptation metrics and insights."""
    resp = client.get("/api/performance/learning")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_version" in data
    assert "insights" in data
    assert isinstance(data["insights"], list)
    assert "sector_performance" in data
    assert "regime_performance" in data
