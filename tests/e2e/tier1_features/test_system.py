"""Tier 1 Feature Coverage: System Configuration, Model Mappings & Self-Healing.

Covers:
- Safe sanitized system config with masked secrets (GET /api/system/config)
- Model-to-agent role mappings (GET /api/system/models)
- Strategy DNA version history (GET /api/system/strategies)
- Self-healing event audit logs (GET /api/system/healing)
- Logging manual healing action (POST /api/system/healing/log)
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_get_system_config_secrets_masked(client: E2EClient):
    """Verify GET /api/system/config masks all sensitive credentials."""
    resp = client.get_system_config()
    assert resp.status_code == 200
    config = resp.json()

    assert "trading_mode" in config
    assert "secrets_status" in config
    secrets = config["secrets_status"]

    # Verify no raw unmasked keys are leaked
    for key_name, status_str in secrets.items():
        assert "masked" in status_str or "configured" in status_str
        assert not status_str.startswith("AIzaSy") or "****" in status_str


def test_get_system_model_mappings(client: E2EClient):
    """Verify GET /api/system/models returns active provider and model per role."""
    resp = client.get_system_models()
    assert resp.status_code == 200
    data = resp.json()

    assert "mappings" in data
    mappings = data["mappings"]
    assert "analyst_team" in mappings
    assert "research_judge" in mappings
    assert "risk_judge" in mappings

    for role, conf in mappings.items():
        assert "provider" in conf
        assert "model" in conf


def test_get_strategy_dna_versions(client: E2EClient):
    """Verify GET /api/system/strategies returns active strategy DNA and historical records."""
    resp = client.get_system_strategies()
    assert resp.status_code == 200
    data = resp.json()

    assert "active" in data
    assert "history" in data
    active = data["active"]
    assert "version" in active
    assert "dna_yaml" in active
    assert active["active"] is True


def test_get_self_healing_events(client: E2EClient):
    """Verify GET /api/system/healing returns recent automated healing actions."""
    resp = client.get_system_healing(limit=10)
    assert resp.status_code == 200
    data = resp.json()

    assert "events" in data
    assert isinstance(data["events"], list)
    if len(data["events"]) > 0:
        event = data["events"][0]
        assert "component" in event
        assert "event_type" in event
        assert "action_taken" in event
        assert "resolved" in event


def test_log_manual_healing_event(client: E2EClient):
    """Verify POST /api/system/healing/log records a self-healing action."""
    resp = client.log_system_healing(
        component="websocket",
        event_type="reconnect_trigger",
        description="Manual socket reset test",
        action_taken="Forced reconnect cycle",
        resolved=True,
        metadata={"trigger": "e2e_test"},
    )
    assert resp.status_code == 200
    result = resp.json()

    assert result["status"] == "logged"
    assert "event" in result
    assert result["event"]["component"] == "websocket"
    assert result["event"]["resolved"] is True
