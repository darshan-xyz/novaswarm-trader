"""Tier 1 Feature Coverage: Performance Analytics & Model Accuracy Breakdown.

Covers:
- Portfolio metrics (GET /api/performance/metrics)
- Daily snapshots time-series (GET /api/performance/daily-snapshots)
- Daily snapshots days query parameter
- Per-model accuracy breakdown (GET /api/performance/models)
- Strategy learning curve & adaptation insights (GET /api/performance/learning)
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_get_performance_metrics_schema(client: E2EClient):
    """Verify GET /api/performance/metrics returns Sharpe, max drawdown, win rate, and total return."""
    resp = client.get_performance_metrics()
    assert resp.status_code == 200
    metrics = resp.json()

    required = [
        "portfolio_value",
        "initial_capital",
        "total_return_pct",
        "day_pnl",
        "win_rate",
        "sharpe_ratio",
        "max_drawdown_pct",
        "profit_factor",
        "total_trades",
    ]
    for key in required:
        assert key in metrics, f"Missing metric key: {key}"

    assert metrics["portfolio_value"] > 0
    assert 0.0 <= metrics["win_rate"] <= 100.0
    assert metrics["max_drawdown_pct"] >= 0.0


def test_get_daily_snapshots_time_series(client: E2EClient):
    """Verify GET /api/performance/daily-snapshots returns chronological equity data."""
    resp = client.get_daily_snapshots(days=30)
    assert resp.status_code == 200
    data = resp.json()

    assert "snapshots" in data
    assert isinstance(data["snapshots"], list)
    assert len(data["snapshots"]) >= 1

    first = data["snapshots"][0]
    for key in ("date", "portfolio_value", "cash", "day_pnl", "max_drawdown_pct"):
        assert key in first, f"Snapshot missing key: {key}"


def test_get_daily_snapshots_days_filter(client: E2EClient):
    """Verify GET /api/performance/daily-snapshots respects 'days' parameter."""
    resp_7 = client.get_daily_snapshots(days=7)
    assert resp_7.status_code == 200
    snapshots_7 = resp_7.json()["snapshots"]
    assert len(snapshots_7) <= 7


def test_get_model_prediction_accuracy(client: E2EClient):
    """Verify GET /api/performance/models returns per-model accuracy breakdown."""
    resp = client.get_performance_models()
    assert resp.status_code == 200
    data = resp.json()

    assert "models" in data
    models = data["models"]
    assert len(models) >= 1

    model_names = [m["model_name"] for m in models]
    assert any("claude" in name for name in model_names)
    assert any("gemini" in name for name in model_names)

    for m in models:
        assert "total_predictions" in m
        assert "accuracy_pct" in m
        assert 0.0 <= m["accuracy_pct"] <= 100.0


def test_get_performance_learning_insights(client: E2EClient):
    """Verify GET /api/performance/learning returns learning curve generations and textual insights."""
    resp = client.get_performance_learning()
    assert resp.status_code == 200
    data = resp.json()

    assert "learning_curve" in data
    assert isinstance(data["learning_curve"], list)
    assert "insights" in data
    assert isinstance(data["insights"], list)
    assert len(data["insights"]) >= 1
