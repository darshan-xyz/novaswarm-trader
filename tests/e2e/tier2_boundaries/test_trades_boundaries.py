"""Tier 2 Boundary & Corner Cases: Trades History & Analytics.

Covers:
- Non-existent trade ID returns HTTP 404
- Extreme offset pagination beyond total count returns empty list with valid total
- Invalid limit=0 returns HTTP 422
- Limit exceeding max 500 returns HTTP 422
- Malformed / non-existent symbol query returns HTTP 200 with empty list
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_trade_not_found_returns_404(client: E2EClient):
    """Verify querying a non-existent UUID returns HTTP 404."""
    resp = client.get_trade("00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    data = resp.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_trade_extreme_offset_returns_empty_list(client: E2EClient):
    """Verify offset far beyond total records returns empty list without error."""
    resp = client.list_trades(limit=50, offset=1_000_000)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] == []
    assert data["total"] >= 0
    assert data["offset"] == 1_000_000


def test_trade_zero_limit_returns_422(client: E2EClient):
    """Verify limit=0 violates validation constraints and returns HTTP 422."""
    resp = client.list_trades(limit=0)
    assert resp.status_code == 422


def test_trade_limit_exceeding_max_returns_422(client: E2EClient):
    """Verify limit > 500 ceiling returns HTTP 422."""
    resp = client.list_trades(limit=501)
    assert resp.status_code == 422


def test_trade_non_existent_symbol_returns_empty(client: E2EClient):
    """Verify querying an un-traded symbol returns HTTP 200 with empty array."""
    resp = client.list_trades(symbol="NONEXISTENT_SYMBOL_XYZ")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] == []
    assert data["total"] == 0
