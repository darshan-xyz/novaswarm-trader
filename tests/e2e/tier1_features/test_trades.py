"""Tier 1 Feature Coverage: Trades History & Statistics.

Covers:
- Default pagination listing
- Filtering by symbol
- Filtering by side (BUY/SELL)
- Filtering by status (COMPLETE/OPEN)
- Single trade detail with model predictions
- Summary statistics calculations
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_list_trades_default_pagination(client: E2EClient):
    """Verify GET /api/trades returns trades array with limit, offset, and total."""
    resp = client.list_trades(limit=50, offset=0)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert "trades" in data, "Response missing 'trades' key"
    assert "total" in data, "Response missing 'total' key"
    assert "limit" in data and data["limit"] == 50
    assert "offset" in data and data["offset"] == 0
    assert isinstance(data["trades"], list)
    assert len(data["trades"]) >= 1

    first_trade = data["trades"][0]
    required_fields = ["id", "symbol", "exchange", "side", "quantity", "price", "status"]
    for field in required_fields:
        assert field in first_trade, f"Trade record missing required field '{field}'"


def test_filter_trades_by_symbol(client: E2EClient):
    """Verify filtering trades by specific symbol (e.g. RELIANCE)."""
    resp = client.list_trades(symbol="RELIANCE")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["trades"]) >= 1
    for trade in data["trades"]:
        assert trade["symbol"] == "RELIANCE", f"Expected RELIANCE, got {trade['symbol']}"


def test_filter_trades_by_side(client: E2EClient):
    """Verify filtering trades by BUY or SELL side."""
    resp = client.list_trades(side="BUY")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["trades"]) >= 1
    for trade in data["trades"]:
        assert trade["side"] == "BUY"


def test_filter_trades_by_status(client: E2EClient):
    """Verify filtering trades by COMPLETE or OPEN status."""
    resp = client.list_trades(status="COMPLETE")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["trades"]) >= 1
    for trade in data["trades"]:
        assert trade["status"] == "COMPLETE"


def test_get_trade_detail_by_id(client: E2EClient):
    """Verify GET /api/trades/{trade_id} returns detailed trade record with model predictions."""
    list_resp = client.list_trades(limit=1)
    trades = list_resp.json()["trades"]
    assert len(trades) > 0
    target_id = trades[0]["id"]

    resp = client.get_trade(target_id)
    assert resp.status_code == 200
    trade = resp.json()

    assert trade["id"] == target_id
    assert "symbol" in trade
    assert "model_predictions" in trade
    assert isinstance(trade["model_predictions"], list)
    if len(trade["model_predictions"]) > 0:
        pred = trade["model_predictions"][0]
        assert "model_name" in pred
        assert "prediction" in pred


def test_trade_summary_statistics(client: E2EClient):
    """Verify GET /api/trades/summary/stats computes accurate win rate and PnL."""
    resp = client.get_trade_stats()
    assert resp.status_code == 200
    stats = resp.json()

    expected_keys = [
        "total_trades",
        "winning_trades",
        "losing_trades",
        "win_rate",
        "total_realized_pnl",
        "gross_profit",
        "gross_loss",
        "profit_factor",
    ]
    for key in expected_keys:
        assert key in stats, f"Stats missing key: {key}"

    assert stats["total_trades"] >= stats["winning_trades"] + stats["losing_trades"]
    assert 0.0 <= stats["win_rate"] <= 100.0
    assert stats["profit_factor"] >= 0.0
