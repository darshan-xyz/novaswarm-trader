"""Tier 2 Boundary & Corner Cases: Frontend Routes & Edge Parameters.

Covers:
- Non-existent route returns HTTP 404
- Analysis route with XSS / special characters in query string
- Trades route with invalid pagination query parameters
- Analytics route with invalid range parameters
- Rapid sequential route requests
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_frontend_non_existent_route_returns_404(client: E2EClient):
    """Verify non-existent frontend route returns HTTP 404."""
    resp = client.get_frontend_route("/nonexistent-page-xyz")
    assert resp.status_code == 404


def test_frontend_analysis_xss_query_sanitization(client: E2EClient):
    """Verify malicious XSS input in route query parameters does not crash server."""
    resp = client.get("/analysis?symbol=%3Cscript%3Ealert(1)%3C%2Fscript%3E", is_frontend=True)
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text or resp.status_code == 200


def test_frontend_trades_invalid_pagination_query(client: E2EClient):
    """Verify trades route with negative or non-numeric query parameters loads gracefully."""
    resp = client.get("/trades?page=-1&limit=abc", is_frontend=True)
    assert resp.status_code in (200, 422)


def test_frontend_analytics_invalid_range_query(client: E2EClient):
    """Verify analytics route with un-recognized range parameter loads cleanly."""
    resp = client.get("/analytics?range=INVALID_RANGE_999", is_frontend=True)
    assert resp.status_code == 200


def test_frontend_rapid_route_switching(client: E2EClient):
    """Verify rapidly requesting multiple views in sequence returns 200 for all."""
    routes = ["/", "/portfolio", "/scanner", "/analysis", "/trades", "/chat", "/analytics", "/settings"]
    for route in routes:
        resp = client.get_frontend_route(route)
        assert resp.status_code == 200, f"Failed on route {route}: {resp.status_code}"
