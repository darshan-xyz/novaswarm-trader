"""Tier 2 Boundary & Corner Cases: Analysis & SSE Stream.

Covers:
- Non-existent job ID returns 404 for GET /api/analysis/{job_id}
- Non-existent job ID returns 404 for SSE stream /api/analysis/{job_id}/stream
- Malformed symbol (empty or special characters) returns 422
- Lookback days out of range (negative or >365) returns 422
- Replay buffer on finished job emits all buffered events correctly
"""

from __future__ import annotations

import pytest

from tests.e2e.client import E2EClient


def test_analysis_job_not_found_status_404(client: E2EClient):
    """Verify querying non-existent job ID status returns HTTP 404."""
    resp = client.get_analysis_status("nonexistent-job-uuid-12345")
    assert resp.status_code == 404


def test_analysis_job_not_found_stream_404(client: E2EClient):
    """Verify streaming from non-existent job ID returns HTTP 404."""
    resp = client.get("/api/analysis/nonexistent-job-uuid-12345/stream")
    assert resp.status_code == 404


def test_analysis_start_invalid_symbol_422(client: E2EClient):
    """Verify empty or invalid symbol payload returns HTTP 422."""
    resp = client.start_analysis(symbol="")
    assert resp.status_code == 422

    resp_special = client.start_analysis(symbol="INVALID$$%%^^")
    assert resp_special.status_code == 422


def test_analysis_start_invalid_lookback_days_422(client: E2EClient):
    """Verify negative or excessive lookback days (>365) returns HTTP 422."""
    resp_neg = client.start_analysis(symbol="RELIANCE", lookback_days=-5)
    assert resp_neg.status_code == 422

    resp_high = client.start_analysis(symbol="RELIANCE", lookback_days=400)
    assert resp_high.status_code == 422


def test_analysis_stream_replay_buffer_finished_job(client: E2EClient):
    """Verify late-connecting client to completed job receives all replayed events."""
    start_resp = client.start_analysis(symbol="RELIANCE")
    job_id = start_resp.json()["job_id"]

    # First stream consumes
    events1 = client.stream_analysis(job_id, max_events=15)
    assert len(events1) >= 5

    # Second stream connects after job is already completed
    events2 = client.stream_analysis(job_id, max_events=15)
    assert len(events2) >= 5

    types1 = [e["event"] for e in events1 if e["event"] != "comment"]
    types2 = [e["event"] for e in events2 if e["event"] != "comment"]
    assert types1 == types2, "Late-joiner replay buffer did not match initial stream"
