"""Tier 1 Feature Coverage: Agent BM25 Memory & Trade Reflections.

Covers:
- Listing canonical 5 memory roles (GET /api/memory/roles)
- Retrieving memories by role (GET /api/memory/role/{role})
- Performing BM25 similarity query (POST /api/memory/query)
- Retrieving trade reflections (GET /api/memory/reflections)
- Filtering reflections by symbol
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_get_memory_roles_returns_canonical_five(client: E2EClient):
    """Verify GET /api/memory/roles lists the canonical 5 agent memory roles."""
    resp = client.get_memory_roles()
    assert resp.status_code == 200
    data = resp.json()

    assert "roles" in data
    roles = data["roles"]
    expected_roles = [
        "bull_memory",
        "bear_memory",
        "trader_memory",
        "invest_judge_memory",
        "risk_manager_memory",
    ]
    for expected in expected_roles:
        assert expected in roles, f"Canonical role '{expected}' missing from /api/memory/roles"


def test_get_memory_by_role_entries(client: E2EClient):
    """Verify GET /api/memory/role/{role} retrieves memory situations and recommendations."""
    resp = client.get_memory_by_role("bull_memory", limit=10)
    assert resp.status_code == 200
    data = resp.json()

    assert data["role"] == "bull_memory"
    assert "memories" in data
    assert isinstance(data["memories"], list)
    if len(data["memories"]) > 0:
        entry = data["memories"][0]
        assert "situation" in entry
        assert "recommendation" in entry


def test_query_bm25_memory_situation(client: E2EClient):
    """Verify POST /api/memory/query performs BM25-like search and returns ranked matches."""
    resp = client.query_memory(
        role="risk_manager_memory",
        query="daily drawdown loss limit",
        top_k=2,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["role"] == "risk_manager_memory"
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) <= 2

    if len(data["results"]) > 0:
        top_result = data["results"][0]
        assert "situation" in top_result
        assert "recommendation" in top_result
        assert "similarity_score" in top_result
        assert 0.0 <= top_result["similarity_score"] <= 1.0


def test_get_trade_reflections(client: E2EClient):
    """Verify GET /api/memory/reflections returns historical trade reflection notes."""
    resp = client.get_reflections(limit=10)
    assert resp.status_code == 200
    data = resp.json()

    assert "reflections" in data
    assert isinstance(data["reflections"], list)
    if len(data["reflections"]) > 0:
        first = data["reflections"][0]
        assert "symbol" in first
        assert "reflection" in first
        assert "pnl" in first


def test_filter_reflections_by_symbol(client: E2EClient):
    """Verify filtering trade reflections by stock symbol."""
    resp = client.get_reflections(symbol="RELIANCE", limit=5)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["reflections"]) >= 1
    for item in data["reflections"]:
        assert item["symbol"] == "RELIANCE"
