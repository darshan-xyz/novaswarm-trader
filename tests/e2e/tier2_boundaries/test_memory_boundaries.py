"""Tier 2 Boundary & Corner Cases: Agent Memory & Reflection Store.

Covers:
- Querying an unknown memory role returns HTTP 404
- Extreme top_k boundary values (top_k=0 and top_k=500)
- Invalid negative top_k returns HTTP 422
- Reflection query for un-traded symbol returns HTTP 200 with empty array
- Empty reflection query with zero or negative limit returns HTTP 422
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_memory_unknown_role_returns_404(client: E2EClient):
    """Verify querying non-existent memory role returns HTTP 404."""
    resp = client.get_memory_by_role("invalid_fictional_role")
    assert resp.status_code == 404
    assert "unknown memory role" in resp.json()["detail"].lower()


def test_memory_query_unknown_role_returns_404(client: E2EClient):
    """Verify POST /api/memory/query with invalid role returns HTTP 404."""
    resp = client.query_memory(role="nonexistent_role", query="test query", top_k=3)
    assert resp.status_code == 404


def test_memory_query_top_k_boundaries(client: E2EClient):
    """Verify top_k=0 and top_k=500 are handled properly within boundary constraints."""
    # top_k=0 returns 0 results
    resp_0 = client.query_memory(role="bull_memory", query="momentum", top_k=0)
    assert resp_0.status_code == 200
    assert resp_0.json()["results"] == []

    # top_k=500 returns bounded results without failure
    resp_500 = client.query_memory(role="bull_memory", query="momentum", top_k=500)
    assert resp_500.status_code == 200
    assert isinstance(resp_500.json()["results"], list)


def test_memory_query_negative_top_k_returns_422(client: E2EClient):
    """Verify negative top_k returns validation error 422."""
    resp = client.query_memory(role="bull_memory", query="momentum", top_k=-1)
    assert resp.status_code == 422


def test_reflections_untraded_symbol_returns_empty_and_zero_limit_422(client: E2EClient):
    """Verify untraded symbol returns empty reflections and limit<=0 returns 422."""
    resp_empty = client.get_reflections(symbol="UNTRADED_SYMBOL")
    assert resp_empty.status_code == 200
    assert resp_empty.json()["reflections"] == []

    resp_invalid_limit = client.get_reflections(limit=0)
    assert resp_invalid_limit.status_code == 422
