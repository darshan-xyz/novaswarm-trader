"""Tier 2 Boundary & Corner Cases: Performance Metrics & Snapshots.

Covers:
- Snapshots with days=0 returns HTTP 422
- Snapshots with inverted date range (start_date > end_date) returns HTTP 422
- High days parameter clamped cleanly
- Resilient calculation of metrics when total_trades is small or zero
- Performance metrics precision and range compliance
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_daily_snapshots_zero_days_returns_422(client: E2EClient):
    """Verify requesting 0 days of snapshots returns HTTP 422."""
    resp = client.get_daily_snapshots(days=0)
    assert resp.status_code == 422


def test_daily_snapshots_negative_days_returns_422(client: E2EClient):
    """Verify negative days value returns HTTP 422."""
    resp = client.get_daily_snapshots(days=-10)
    assert resp.status_code == 422


def test_daily_snapshots_inverted_date_range_returns_422(client: E2EClient):
    """Verify start_date after end_date returns HTTP 422."""
    resp = client.get_daily_snapshots(start_date="2026-09-25", end_date="2026-09-20")
    assert resp.status_code == 422


def test_daily_snapshots_large_days_capped(client: E2EClient):
    """Verify large days parameter (e.g. 365) returns capped available snapshots cleanly."""
    resp = client.get_daily_snapshots(days=365)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["snapshots"]) <= 30


def test_performance_metrics_numerical_integrity(client: E2EClient):
    """Verify all floating point metrics fall within mathematically valid bounds."""
    resp = client.get_performance_metrics()
    assert resp.status_code == 200
    m = resp.json()

    # Win rate must be 0-100%
    assert 0.0 <= m["win_rate"] <= 100.0
    # Max drawdown must be >= 0
    assert m["max_drawdown_pct"] >= 0.0
    # Portfolio value cannot be negative
    assert m["portfolio_value"] > 0
    # Winning + losing cannot exceed total trades
    assert m["winning_trades"] + m["losing_trades"] <= m["total_trades"]
