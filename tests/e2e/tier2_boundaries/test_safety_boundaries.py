"""Tier 2 Boundary & Corner Cases: Pre-Trade Safety Enforcement.

Covers:
- Zero quantity returns HTTP 422
- Negative price returns HTTP 422
- Inverted stop loss (stop_loss >= entry price for BUY) rejected
- Single order value exceeding ceiling ₹500,000 rejected
- Invalid action (not BUY or SELL) returns HTTP 422
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_safety_zero_quantity_returns_422(client: E2EClient):
    """Verify quantity=0 returns HTTP 422 validation error."""
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=0,
        price=2800.0,
        stop_loss=2720.0,
    )
    assert resp.status_code == 422


def test_safety_negative_price_returns_422(client: E2EClient):
    """Verify negative price returns HTTP 422 validation error."""
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=10,
        price=-2800.0,
        stop_loss=2720.0,
    )
    assert resp.status_code == 422


def test_safety_inverted_stop_loss_rejected(client: E2EClient):
    """Verify BUY order with stop_loss >= entry_price is rejected."""
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=10,
        price=2800.0,
        stop_loss=2850.0,  # Higher than entry price!
    )
    assert resp.status_code == 200
    sim = resp.json()
    assert sim["passed"] is False
    assert any("cannot be >=" in r for r in sim["rejections"])


def test_safety_order_value_exceeding_500k_ceiling_rejected(client: E2EClient):
    """Verify order value exceeding the absolute ₹500,000 ceiling is rejected."""
    # 200 shares @ ₹2800 = ₹560,000 (exceeds ₹500,000 ceiling)
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=200,
        price=2800.0,
        stop_loss=2720.0,
    )
    assert resp.status_code == 200
    sim = resp.json()
    assert sim["passed"] is False
    assert any("exceeds ceiling" in r for r in sim["rejections"])


def test_safety_invalid_action_returns_422(client: E2EClient):
    """Verify action other than BUY or SELL (e.g. HOLD) returns HTTP 422."""
    resp = client.simulate_safety(
        symbol="RELIANCE",
        action="HOLD",
        quantity=10,
        price=2800.0,
        stop_loss=2720.0,
    )
    assert resp.status_code == 422
