"""Unit tests for skopaq/api/trades_router.py."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skopaq.api.trades_router import router
from skopaq.db.models import ModelPredictionRecord, TradeRecord


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_trades_offline(client):
    """When Supabase is not configured, list_trades returns HTTP 200 with an empty list."""
    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/trades?limit=25&offset=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trades"] == []
        assert data["total"] == 0
        assert data["limit"] == 25
        assert data["offset"] == 5


def test_list_trades_with_data(client):
    """When Supabase is active, list_trades returns populated records with query filtering."""
    fake_trade_id = uuid4()
    mock_row = {
        "id": str(fake_trade_id),
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "side": "BUY",
        "quantity": "10",
        "price": "2500.0",
        "status": "COMPLETE",
        "is_paper": True,
        "pnl": "1250.0",
        "created_at": "2026-09-23T10:00:00Z",
    }

    mock_query = MagicMock()
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.range.return_value = mock_query
    mock_res = MagicMock()
    mock_res.data = [mock_row]
    mock_res.count = 1
    mock_query.execute.return_value = mock_res

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value = mock_query

    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client):
        resp = client.get("/api/trades?symbol=RELIANCE&side=BUY&status=COMPLETE&is_paper=true&strategy=v1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["trades"]) == 1
        assert data["trades"][0]["symbol"] == "RELIANCE"
        assert data["trades"][0]["side"] == "BUY"


def test_get_trade_stats_offline(client):
    """Stats endpoint gracefully returns zero-state defaults when offline."""
    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=None):
        resp = client.get("/api/trades/summary/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 0
        assert data["winning_trades"] == 0
        assert data["win_rate"] == 0.0
        assert data["profit_factor"] == 1.0


def test_get_trade_stats_with_data(client):
    """Stats endpoint calculates win rate, realized P&L, and profit factor correctly."""
    mock_rows = [
        {"pnl": "2000.0", "brokerage": "20.0", "is_paper": True},
        {"pnl": "1000.0", "brokerage": "15.0", "is_paper": False},
        {"pnl": "-1000.0", "brokerage": "20.0", "is_paper": True},
    ]

    mock_query = MagicMock()
    mock_res = MagicMock()
    mock_res.data = mock_rows
    mock_query.execute.return_value = mock_res
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value = mock_query

    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client):
        resp = client.get("/api/trades/summary/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 3
        assert data["paper_trades"] == 2
        assert data["live_trades"] == 1
        assert data["winning_trades"] == 2
        assert data["losing_trades"] == 1
        assert data["win_rate"] == 66.7
        assert data["total_realized_pnl"] == 2000.0
        assert data["total_brokerage"] == 55.0
        assert data["net_pnl"] == 1945.0
        assert data["gross_profit"] == 3000.0
        assert data["gross_loss"] == 1000.0
        assert data["profit_factor"] == 3.0


def test_get_trade_by_id_invalid_uuid(client):
    resp = client.get("/api/trades/invalid-uuid-string")
    assert resp.status_code == 400
    assert "Invalid UUID format" in resp.json()["detail"]


def test_get_trade_by_id_not_found(client):
    t_id = str(uuid4())
    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=None):
        resp = client.get(f"/api/trades/{t_id}")
        assert resp.status_code == 404


def test_get_trade_by_id_success(client):
    t_id = uuid4()
    mock_trade = TradeRecord(
        id=t_id,
        symbol="TCS",
        exchange="NSE",
        side="BUY",
        quantity=Decimal("15"),
        price=Decimal("3500.0"),
        status="COMPLETE",
    )
    mock_pred = ModelPredictionRecord(
        trade_id=t_id,
        model_name="claude-3-5-sonnet",
        prediction="BUY",
        confidence=Decimal("85"),
    )

    mock_client = MagicMock()
    with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
         patch("skopaq.api.trades_router.TradeRepository.get_by_id", return_value=mock_trade), \
         patch("skopaq.api.trades_router.PredictionRepository.get_by_trade", return_value=[mock_pred]):
        resp = client.get(f"/api/trades/{t_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(t_id)
        assert data["symbol"] == "TCS"
        assert len(data["predictions"]) == 1
        assert data["predictions"][0]["model_name"] == "claude-3-5-sonnet"
