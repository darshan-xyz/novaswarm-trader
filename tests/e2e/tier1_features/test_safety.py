"""Tier 1 Feature Coverage: Pre-Trade Safety Simulation & Risk Rules.

Covers:
- Frozen safety rules retrieval (GET /api/safety/rules)
- Compliant order simulation passes (POST /api/safety/simulate)
- Oversized position order simulation rejected
- Missing or insufficient stop-loss rejected
- Intraday safety status monitoring (GET /api/safety/status)
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_get_frozen_safety_rules(client: E2EClient):
    """Verify GET /api/safety/rules returns immutable safety parameters and thresholds."""
    resp = client.get_safety_rules()
    assert resp.status_code == 200
    data = resp.json()

    assert "rules" in data
    rules = data["rules"]
    assert "max_position_pct" in rules
    assert "max_daily_loss_pct" in rules
    assert "max_order_value_inr" in rules
    assert "min_stop_loss_pct" in rules
    assert rules["max_position_pct"] == 0.15
    assert rules["max_order_value_inr"] == 500000.0


def test_simulate_safety_compliant_order_passes(client: E2EClient):
    """Verify standard order within safety boundaries passes with empty rejections."""
    # 20 shares @ ₹2800 = ₹56,000 (5.6% of ₹1M capital, well under 15% limit)
    # Stop-loss at ₹2720 = 2.85% stop-loss (well above 2.0% min)
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=20,
        price=2800.0,
        stop_loss=2720.0,
        target=2960.0,
        confidence=80,
    )
    assert resp.status_code == 200
    sim = resp.json()

    assert sim["passed"] is True
    assert len(sim["rejections"]) == 0
    assert sim["simulated_order_value"] == 56000.0
    assert sim["risk_pct"] == 5.6


def test_simulate_safety_oversized_position_rejected(client: E2EClient):
    """Verify order exceeding 15% portfolio allocation is rejected."""
    # 100 shares @ ₹2800 = ₹280,000 (28% of ₹1M capital, exceeding 15% limit)
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=100,
        price=2800.0,
        stop_loss=2720.0,
        target=2960.0,
    )
    assert resp.status_code == 200
    sim = resp.json()

    assert sim["passed"] is False
    assert len(sim["rejections"]) >= 1
    assert any("exceeds max" in r for r in sim["rejections"])


def test_simulate_safety_missing_or_small_stop_loss_rejected(client: E2EClient):
    """Verify order without mandatory stop-loss or with <2% distance is rejected."""
    # Stop loss at ₹2790 on ₹2800 entry = 0.35% distance (< 2.0% min required)
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=10,
        price=2800.0,
        stop_loss=2790.0,
        target=2900.0,
    )
    assert resp.status_code == 200
    sim = resp.json()

    assert sim["passed"] is False
    assert len(sim["rejections"]) >= 1
    assert any("below minimum" in r for r in sim["rejections"])


def test_get_safety_status_intraday(client: E2EClient):
    """Verify GET /api/safety/status returns live circuit-breaker and order-rate state."""
    resp = client.get_safety_status()
    assert resp.status_code == 200
    status_data = resp.json()

    required = [
        "circuit_breaker_tripped",
        "daily_drawdown_pct",
        "open_positions_count",
        "max_allowed_positions",
        "orders_last_minute",
        "max_orders_per_minute",
    ]
    for key in required:
        assert key in status_data, f"Missing safety status key: {key}"

    assert status_data["circuit_breaker_tripped"] is False
    assert status_data["orders_last_minute"] <= status_data["max_orders_per_minute"]
