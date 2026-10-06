"""Tier 3: Cross-Feature Combinations & Pipeline Interactions.

Covers:
- T3.1: Analysis -> Decision Card -> Safety Pre-Trade Simulation -> Sizing Validation
- T3.2: Market Scanner Candidate -> Trigger Analysis -> Stream Verification -> Decision Card
- T3.3: Trade Record -> Memory Reflection Store -> BM25 Recall Search
- T3.4: Chat Assistant Conversation -> Analysis Tool Invocation -> Recommendation Card
- T3.5: Trades Summary Stats -> Performance Metrics Alignment
- T3.6: Safety Rejection Event -> System Self-Healing Audit Trail Logging
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_cross_feature_analysis_to_safety_simulation(client: E2EClient):
    """Pipeline 1: Analysis swarm outputs decision_card, which is piped to safety simulation."""
    # Step 1: Start analysis on symbol
    start_resp = client.start_analysis(symbol="RELIANCE", urgency="high")
    assert start_resp.status_code in (200, 202)
    job_id = start_resp.json()["job_id"]

    # Step 2: Stream events to capture decision card
    events = client.stream_analysis(job_id, max_events=20)
    decision_ev = next((e for e in events if e["event"] == "decision_card"), None)
    assert decision_ev is not None, "decision_card event was not emitted by analysis stream"

    card = decision_ev["data"]
    assert card["verdict"] in ("BUY", "SELL")
    assert card["entry_price"] > 0
    assert card["stop_loss"] > 0
    assert card["position_size"] > 0

    # Step 3: Pipe proposed trade parameters into pre-trade safety simulation
    sim_resp = client.simulate_safety(
        symbol="RELIANCE",
        action=card["verdict"],
        quantity=card["position_size"],
        price=card["entry_price"],
        stop_loss=card["stop_loss"],
        target=card["target"],
        confidence=card["confidence"],
    )
    assert sim_resp.status_code == 200
    sim_result = sim_resp.json()

    # Step 4: Verify safety check accepts the properly sized trade
    assert sim_result["passed"] is True, f"Safety check rejected: {sim_result['rejections']}"
    assert sim_result["simulated_order_value"] == card["position_size"] * card["entry_price"]


def test_cross_feature_scanner_to_analysis_pipeline(client: E2EClient):
    """Pipeline 2: Market scanner candidates trigger swarm analysis."""
    # Step 1: Trigger scan and get top candidate
    scan_resp = client.trigger_scan()
    assert scan_resp.status_code == 200

    cand_resp = client.get_scanner_candidates()
    assert cand_resp.status_code == 200
    candidates = cand_resp.json()["candidates"]
    assert len(candidates) >= 1

    top_candidate = candidates[0]
    symbol = top_candidate["symbol"]
    assert top_candidate["urgency"] in ("HIGH", "NORMAL", "LOW")

    # Step 2: Trigger swarm analysis for this flagged candidate
    analysis_resp = client.start_analysis(symbol=symbol)
    assert analysis_resp.status_code in (200, 202)
    job_id = analysis_resp.json()["job_id"]

    # Step 3: Stream and verify job starts and completes
    events = client.stream_analysis(job_id, max_events=20)
    event_types = [e["event"] for e in events]
    assert "job_started" in event_types
    assert "job_completed" in event_types


def test_cross_feature_trade_logging_to_memory_reflection(client: E2EClient):
    """Pipeline 3: Closed trade reflections integrate with BM25 memory retrieval."""
    # Step 1: Get recent closed trades
    trades_resp = client.list_trades(status="COMPLETE")
    assert trades_resp.status_code == 200
    trades = trades_resp.json()["trades"]
    assert len(trades) >= 1

    symbol = trades[0]["symbol"]

    # Step 2: Check reflections for this symbol
    refl_resp = client.get_reflections(symbol=symbol)
    assert refl_resp.status_code == 200
    reflections = refl_resp.json()["reflections"]
    assert len(reflections) >= 1

    target_reflection = reflections[0]["reflection"]

    # Step 3: Query BM25 memory using situation keywords from reflection
    query_resp = client.query_memory(
        role="bull_memory",
        query=target_reflection[:50],
        top_k=2,
    )
    assert query_resp.status_code == 200
    results = query_resp.json()["results"]
    assert isinstance(results, list)


def test_cross_feature_chat_assistant_triggers_analysis_and_trade(client: E2EClient):
    """Pipeline 4: Chat assistant command invokes analysis tool and reports verdict."""
    resp = client.send_chat_message("Can you analyze RELIANCE for me?")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["tool_calls"]) >= 1
    tool_call = next((t for t in data["tool_calls"] if t["tool"] == "analyze_stock"), None)
    assert tool_call is not None
    assert "BUY" in tool_call["result"] or "Verdict" in tool_call["result"]


def test_cross_feature_trade_closure_to_performance_analytics(client: E2EClient):
    """Pipeline 5: Trades stats and performance metrics maintain mathematical consistency."""
    trade_stats_resp = client.get_trade_stats()
    perf_metrics_resp = client.get_performance_metrics()

    assert trade_stats_resp.status_code == 200
    assert perf_metrics_resp.status_code == 200

    ts = trade_stats_resp.json()
    pm = perf_metrics_resp.json()

    # Total trades count must match across routers
    assert ts["total_trades"] == pm["total_trades"]
    # Win rates must be consistent (within 1% rounding difference)
    assert abs(ts["win_rate"] - pm["win_rate"]) < 1.0


def test_cross_feature_safety_rejection_to_healing_event_logging(client: E2EClient):
    """Pipeline 6: Safety violation triggers self-healing audit trail logging."""
    # Step 1: Simulate oversized order that violates safety envelope
    sim_resp = client.simulate_safety(
        symbol="RELIANCE",
        action="BUY",
        quantity=300,  # 300 * 2800 = 840,000 (exceeds ₹500,000 cap)
        price=2800.0,
        stop_loss=2720.0,
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["passed"] is False

    # Step 2: System automatically or manually logs this safety trip to healing events
    rejection_reason = sim_data["rejections"][0]
    log_resp = client.log_system_healing(
        component="safety_checker",
        event_type="risk_boundary_violation",
        description=f"Order rejected: {rejection_reason}",
        action_taken="Blocked execution and alerted trader",
        resolved=True,
        metadata={"rejections": sim_data["rejections"], "order_value": sim_data["simulated_order_value"]},
    )
    assert log_resp.status_code == 200

    # Step 3: Query healing history to verify audit persistence
    history_resp = client.get_system_healing(component="safety_checker")
    assert history_resp.status_code == 200
    events = history_resp.json()["events"]
    assert len(events) >= 1
    assert any("risk_boundary_violation" in e["event_type"] for e in events)
