"""Tier 1 Feature Coverage: Frontend Application Views.

Covers clean HTTP 200 rendering for all 8 required web views:
1. System Overview Dashboard (/)
2. Portfolio & Open Positions (/portfolio)
3. Market Scanner View (/scanner)
4. Multi-Agent Analysis View (/analysis)
5. Trades History (/trades)
6. Interactive AI Trading Chat (/chat)
7. Performance Analytics (/analytics)
8. Settings & System Health (/settings)
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_frontend_route_overview_dashboard(client: E2EClient):
    """Verify Route / (System Overview Dashboard) returns HTTP 200 with HTML."""
    resp = client.get_frontend_route("/")
    assert resp.status_code == 200
    assert "html" in resp.headers.get("content-type", "").lower()
    assert "System Overview" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_portfolio(client: E2EClient):
    """Verify Route /portfolio (Portfolio & Open Positions) returns HTTP 200."""
    resp = client.get_frontend_route("/portfolio")
    assert resp.status_code == 200
    assert "Portfolio" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_scanner(client: E2EClient):
    """Verify Route /scanner (Market Scanner View) returns HTTP 200."""
    resp = client.get_frontend_route("/scanner")
    assert resp.status_code == 200
    assert "Scanner" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_analysis(client: E2EClient):
    """Verify Route /analysis (Multi-Agent Analysis View) returns HTTP 200."""
    resp = client.get_frontend_route("/analysis")
    assert resp.status_code == 200
    assert "Analysis" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_trades(client: E2EClient):
    """Verify Route /trades (Trades History) returns HTTP 200."""
    resp = client.get_frontend_route("/trades")
    assert resp.status_code == 200
    assert "Trades" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_chat(client: E2EClient):
    """Verify Route /chat (Interactive AI Trading Chat) returns HTTP 200."""
    resp = client.get_frontend_route("/chat")
    assert resp.status_code == 200
    assert "Chat" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_analytics(client: E2EClient):
    """Verify Route /analytics (Performance Analytics) returns HTTP 200."""
    resp = client.get_frontend_route("/analytics")
    assert resp.status_code == 200
    assert "Analytics" in resp.text or "<!DOCTYPE html>" in resp.text


def test_frontend_route_settings(client: E2EClient):
    """Verify Route /settings (Settings & System Health) returns HTTP 200."""
    resp = client.get_frontend_route("/settings")
    assert resp.status_code == 200
    assert "Settings" in resp.text or "<!DOCTYPE html>" in resp.text
