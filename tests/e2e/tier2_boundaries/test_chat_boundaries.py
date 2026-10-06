"""Tier 2 Boundary & Corner Cases: Chat Assistant.

Covers:
- Empty message body returns HTTP 422
- Unknown tool call execution returns HTTP 400 with 'Unknown tool'
- Massive 10,000-character user message payload handled without crash
- New / non-existent session_id automatically initializes fresh session
- Tool execution with empty arguments dictionary succeeds
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_chat_message_empty_body_returns_422(client: E2EClient):
    """Verify empty string message returns HTTP 422 validation error."""
    resp = client.send_chat_message("")
    assert resp.status_code == 422


def test_chat_tool_unknown_tool_returns_400(client: E2EClient):
    """Verify executing an unregistered tool name returns HTTP 400."""
    resp = client.call_chat_tool("nonexistent_fictional_tool")
    assert resp.status_code == 400
    assert "unknown tool" in resp.json()["detail"].lower()


def test_chat_message_massive_payload_stress(client: E2EClient):
    """Verify assistant handles 10,000-character input message without crashing."""
    large_msg = "Please analyze this trading scenario: " + ("volatility is high and RSI is 70; " * 300)
    assert len(large_msg) > 10_000

    resp = client.send_chat_message(large_msg)
    assert resp.status_code == 200
    assert len(resp.json()["message"]) > 0


def test_chat_session_fresh_initialization(client: E2EClient):
    """Verify non-existent session_id passed by client initializes a valid session."""
    custom_session_id = "custom-fresh-session-uuid-999"
    resp = client.send_chat_message("Hello from fresh session", session_id=custom_session_id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == custom_session_id


def test_chat_tool_empty_args_succeeds(client: E2EClient):
    """Verify executing tool with empty dictionary args succeeds."""
    resp = client.call_chat_tool(tool="check_status", args={})
    assert resp.status_code == 200
    assert "result" in resp.json()
