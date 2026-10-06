"""Tier 2 Boundary & Corner Cases: System Settings, Models & Healing.

Covers:
- Missing required fields when logging a healing event returns HTTP 422
- Logging healing event with complex arbitrary metadata payload succeeds
- Non-existent healing component filter returns empty list with HTTP 200
- Verification that no unmasked sensitive secrets are returned in system config
- Extreme limit on healing events returns bounded list
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_system_healing_log_missing_fields_returns_422(client: E2EClient):
    """Verify missing required fields (component, event_type) returns HTTP 422."""
    resp = client.post("/api/system/healing/log", json_data={"description": "missing fields"})
    assert resp.status_code == 422


def test_system_healing_log_complex_metadata(client: E2EClient):
    """Verify posting healing event with nested complex metadata preserves payload."""
    complex_meta = {
        "stack_trace": ["line 1", "line 2"],
        "retry_attempts": 3,
        "nested": {"key": "val", "arr": [1, 2, 3]},
    }
    resp = client.log_system_healing(
        component="redis",
        event_type="cache_miss_burst",
        description="Redis latency spike auto-handled",
        action_taken="Fell back to local memory cache",
        resolved=True,
        metadata=complex_meta,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "logged"
    assert data["event"]["metadata"]["retry_attempts"] == 3
    assert data["event"]["metadata"]["nested"]["key"] == "val"


def test_system_healing_non_existent_component_returns_empty(client: E2EClient):
    """Verify filtering healing events by non-existent component returns empty array."""
    resp = client.get_system_healing(component="nonexistent_component_xyz")
    assert resp.status_code == 200
    assert resp.json()["events"] == []


def test_system_config_strict_masking_audit(client: E2EClient):
    """Audit system config to ensure zero raw API secret substrings appear in output."""
    resp = client.get_system_config()
    assert resp.status_code == 200
    config_str = resp.text

    # None of these raw secret prefixes should ever be exposed unmasked
    forbidden_substrings = [
        "AIzaSyB",
        "sk-ant-api03",
        "pplx-live-",
        "xai-prod-",
    ]
    for forbidden in forbidden_substrings:
        assert forbidden not in config_str, f"Found unmasked secret pattern: {forbidden}"


def test_system_healing_limit_boundaries(client: E2EClient):
    """Verify limit=1 returns at most 1 healing event."""
    resp = client.get_system_healing(limit=1)
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) <= 1
