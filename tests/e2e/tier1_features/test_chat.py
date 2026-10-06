"""Tier 1 Feature Coverage: Interactive AI Trading Chat & Tool Invocations.

Covers:
- Sending a message and receiving AI response (POST /api/chat/message)
- Session continuity across multiple conversation turns
- Direct tool execution (POST /api/chat/tool)
- Assistant automatic tool call for portfolio status
- Assistant automatic tool call for stock analysis
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_send_chat_message_turnaround(client: E2EClient):
    """Verify sending a basic message returns conversational response and session_id."""
    resp = client.send_chat_message("Hello, who are you and what can you do?")
    assert resp.status_code == 200
    data = resp.json()

    assert "message" in data
    assert "session_id" in data
    assert len(data["message"]) > 0
    assert "tool_calls" in data


def test_chat_session_continuity(client: E2EClient):
    """Verify multi-turn conversation maintains session state via session_id."""
    first_resp = client.send_chat_message("Let's analyze Indian equities.")
    assert first_resp.status_code == 200
    session_id = first_resp.json()["session_id"]
    assert session_id

    second_resp = client.send_chat_message("Can you check my portfolio?", session_id=session_id)
    assert second_resp.status_code == 200
    second_data = second_resp.json()

    assert second_data["session_id"] == session_id
    assert "portfolio" in second_data["message"].lower() or len(second_data["tool_calls"]) > 0


def test_chat_direct_tool_execution(client: E2EClient):
    """Verify POST /api/chat/tool directly executes trading tools."""
    resp = client.call_chat_tool(tool="get_portfolio")
    assert resp.status_code == 200
    data = resp.json()

    assert "result" in data
    assert "Portfolio" in data["result"]


def test_chat_message_auto_triggers_portfolio_tool(client: E2EClient):
    """Verify natural language query about positions auto-triggers get_portfolio tool."""
    resp = client.send_chat_message("What are my open positions and cash balance?")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["tool_calls"]) >= 1
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "get_portfolio" in tool_names


def test_chat_message_auto_triggers_analysis_tool(client: E2EClient):
    """Verify natural language prompt 'analyze RELIANCE' triggers analyze_stock tool."""
    resp = client.send_chat_message("Please analyze RELIANCE for swing trading.")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["tool_calls"]) >= 1
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "analyze_stock" in tool_names
    assert "BUY" in data["message"] or "Verdict" in data["message"]
