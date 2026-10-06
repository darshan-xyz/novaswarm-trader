"""Tier 4: Real-World Application Scenarios (End-to-End Trading Workflows).

Covers:
- Scenario 1: The Complete Profitable Breakout Trading Lifecycle (Health -> Scan -> Swarm -> Decision -> Safety -> Portfolio -> Trade History -> Metrics)
- Scenario 2: High-Risk Protection & Circuit Breaker Enforcement Workflow (Over-allocation -> Safety Rejection -> Healing Log -> Chat Explanation)
- Scenario 3: Multi-Model Swarm Disagreement & Consensus Resolution (Model Breakdown -> Debate Rules -> Confidence Threshold -> Decision Card)
- Scenario 4: Network Interruption & Stream Reconnection (Launch -> Mid-stream Disconnect -> Reconnect -> Replay Buffer -> Completion)
- Scenario 5: Strategy Adaptation & Memory Reflection Workflow (Strategy DNA -> Trade Reflections -> BM25 Recall -> Learning Insights)
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_scenario_complete_breakout_trading_lifecycle(client: E2EClient):
    """Scenario 1: End-to-end autonomous swing trading lifecycle on a breakout setup."""
    # Step 1: Health & Broker verification
    health_resp = client.get_health()
    assert health_resp.status_code == 200
    assert health_resp.json()["token_valid"] is True

    status_resp = client.get_status()
    assert status_resp.status_code == 200
    assert status_resp.json()["broker"]["name"] == "INDstocks"

    # Step 2: Market Scanner identifies candidate
    scan_resp = client.trigger_scan()
    assert scan_resp.status_code == 200
    candidates = client.get_scanner_candidates().json()["candidates"]
    assert len(candidates) >= 1
    target = candidates[0]
    symbol = target["symbol"]

    # Step 3: Trigger Multi-Agent Swarm Analysis
    start_resp = client.start_analysis(symbol=symbol, urgency="high")
    job_id = start_resp.json()["job_id"]

    # Step 4: Stream live SSE events
    events = client.stream_analysis(job_id, max_events=25)
    event_types = [e["event"] for e in events]

    assert "job_started" in event_types
    assert "agent_status" in event_types
    assert "agent_report" in event_types
    assert "decision_card" in event_types
    assert "job_completed" in event_types

    decision_card = next(e["data"] for e in events if e["event"] == "decision_card")
    assert decision_card["verdict"] in ("BUY", "SELL", "HOLD")

    # Step 5: Simulate Safety Pre-Trade
    sim_resp = client.simulate_safety(
        symbol=symbol,
        action=decision_card["verdict"],
        quantity=decision_card["position_size"],
        price=decision_card["entry_price"],
        stop_loss=decision_card["stop_loss"],
        target=decision_card["target"],
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["passed"] is True

    # Step 6: Verify Portfolio Cash & Capacity
    portfolio_resp = client.get_portfolio()
    assert portfolio_resp.status_code == 200
    port = portfolio_resp.json()
    assert port["cash"] >= sim_data["simulated_order_value"]

    # Step 7: Verify Performance tracking readiness
    perf_resp = client.get_performance_metrics()
    assert perf_resp.status_code == 200
    assert perf_resp.json()["portfolio_value"] > 0


def test_scenario_risk_containment_and_circuit_breaker_workflow(client: E2EClient):
    """Scenario 2: Pre-trade safety blocks excessive risk and logs audit incident."""
    # Step 1: Intraday status check confirms clean state
    status_resp = client.get_safety_status()
    assert status_resp.status_code == 200
    assert status_resp.json()["circuit_breaker_tripped"] is False

    # Step 2: Attempt hazardous oversized order exceeding ₹500,000 ceiling
    hazard_resp = client.simulate_safety(
        symbol="TCS",
        action="BUY",
        quantity=200,  # 200 * 3800 = ₹760,000 > ₹500,000 ceiling
        price=3800.0,
        stop_loss=3700.0,
    )
    assert hazard_resp.status_code == 200
    hazard_data = hazard_resp.json()
    assert hazard_data["passed"] is False
    assert len(hazard_data["rejections"]) >= 1

    # Step 3: Record safety violation into self-healing audit log
    heal_resp = client.log_system_healing(
        component="safety_checker",
        event_type="order_value_exceeded",
        description=f"Blocked order of ₹{hazard_data['simulated_order_value']:,} exceeding limit",
        action_taken="Rejected order and notified risk team",
        resolved=True,
    )
    assert heal_resp.status_code == 200

    # Step 4: Chat assistant consultation confirms risk rules
    chat_resp = client.send_chat_message("Why was my large TCS trade rejected?")
    assert chat_resp.status_code == 200
    assert len(chat_resp.json()["message"]) > 0


def test_scenario_multi_model_disagreement_and_consensus_resolution(client: E2EClient):
    """Scenario 3: Model accuracy review and swarm debate consensus check."""
    # Step 1: Verify model performance tracking across LLMs
    models_resp = client.get_performance_models()
    assert models_resp.status_code == 200
    models = models_resp.json()["models"]
    assert len(models) >= 3

    # Step 2: Check Research Judge memory for consensus guidelines
    judge_mem_resp = client.get_memory_by_role("invest_judge_memory")
    assert judge_mem_resp.status_code == 200
    memories = judge_mem_resp.json()["memories"]
    assert len(memories) >= 1

    # Step 3: Run analysis on stock and check confidence calibration
    start_resp = client.start_analysis(symbol="INFY")
    job_id = start_resp.json()["job_id"]
    job_status = client.get_analysis_status(job_id).json()

    assert job_status["decision"] is not None
    assert "confidence" in job_status["decision"]
    assert job_status["decision"]["confidence"] >= 60  # Minimum confidence threshold


def test_scenario_network_interruption_and_stream_reconnection(client: E2EClient):
    """Scenario 4: Reconnecting client seamlessly catches up with all streamed events."""
    # Step 1: Start analysis job
    start_resp = client.start_analysis(symbol="HDFCBANK")
    job_id = start_resp.json()["job_id"]

    # Step 2: Client connects and reads partial stream (first 3 events) then disconnects
    events_initial = client.stream_analysis(job_id, max_events=3)
    assert len(events_initial) >= 2

    # Step 3: Reconnect to same job stream
    events_reconnected = client.stream_analysis(job_id, max_events=25)

    # Step 4: Verify all historical events were replayed and job reached terminal state
    event_types = [e["event"] for e in events_reconnected]
    assert "job_started" in event_types
    assert "decision_card" in event_types
    assert "job_completed" in event_types


def test_scenario_strategy_adaptation_and_reflection_workflow(client: E2EClient):
    """Scenario 5: Closed trades generate reflections that feed into learning insights."""
    # Step 1: Check active Strategy DNA
    strat_resp = client.get_system_strategies()
    assert strat_resp.status_code == 200
    active_dna = strat_resp.json()["active"]
    assert active_dna["active"] is True

    # Step 2: Inspect trade reflections
    refl_resp = client.get_reflections(limit=5)
    assert refl_resp.status_code == 200
    reflections = refl_resp.json()["reflections"]
    assert len(reflections) >= 1

    # Step 3: Query memory with reflection lessons
    query_resp = client.query_memory(
        role="risk_manager_memory",
        query="loss protection trailing stop",
        top_k=2,
    )
    assert query_resp.status_code == 200
    results = query_resp.json()["results"]
    assert len(results) >= 1

    # Step 4: Verify performance learning insights reflect adaptation
    learn_resp = client.get_performance_learning()
    assert learn_resp.status_code == 200
    learning_data = learn_resp.json()
    assert len(learning_data["learning_curve"]) >= 2
    assert len(learning_data["insights"]) >= 1
