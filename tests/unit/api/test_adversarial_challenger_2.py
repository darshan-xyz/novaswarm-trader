"""Adversarial stress and edge-case verification tests for Challenger 2.

Covers:
1. Memory router BM25 queries with empty tokens, special characters, non-existent roles, and boundary top_k.
2. Trade summary statistics mathematical alignment with portfolio performance metrics across all edge scenarios.
3. Untested branches and failure modes across trades, memory, safety, system, and analysis routers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skopaq.api.analysis_router import router as analysis_router
from skopaq.api.memory_router import router as memory_router
from skopaq.api.performance_router import router as perf_router
from skopaq.api.safety_router import router as safety_router
from skopaq.api.system_router import router as system_router
from skopaq.api.trades_router import router as trades_router
from skopaq.db.models import AgentMemoryRecord, TradeRecord


@pytest.fixture
def app_client():
    """Mount all API routers on a test FastAPI instance."""
    app = FastAPI()
    app.include_router(memory_router)
    app.include_router(trades_router)
    app.include_router(perf_router)
    app.include_router(safety_router)
    app.include_router(system_router)
    app.include_router(analysis_router)
    return TestClient(app)


# ==============================================================================
# 1. MEMORY ROUTER BM25 ADVERSARIAL TESTS
# ==============================================================================

class TestMemoryRouterAdversarial:
    """Stress-test BM25 scoring, tokenization edge cases, and role lookups."""

    @pytest.fixture
    def mock_memory_corpus(self):
        return AgentMemoryRecord(
            role="bull_memory",
            documents=[
                "NIFTY trading near 200 DMA with heavy IT sector volume and positive earnings",
                "Strong institutional buying in private banks following RBI rate pause",
                "Breakout confirmation above 50-day moving average on RELIANCE",
            ],
            recommendations=[
                "Look for breakout setups in tier-1 IT with ATR-based stops",
                "Initiate long positions on 15m pullback toward VWAP",
                "Buy with trailing stop at 20 EMA",
            ],
            updated_at=datetime.now(timezone.utc),
        )

    def test_bm25_empty_tokens_spaces_only(self, app_client, mock_memory_corpus):
        """Query with whitespace only tokenizes to empty list; should not crash with ZeroDivisionError."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_memory_corpus):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "bull_memory", "query": "   ", "top_k": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "bull_memory"
            assert data["results"] == []

    def test_bm25_special_characters_only(self, app_client, mock_memory_corpus):
        """Query containing only punctuation and special characters tokenizes to [] and returns empty list."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_memory_corpus):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "bull_memory", "query": "!@#$%^&*()_+=-{}[]:;\"'|<>,.?/", "top_k": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["results"] == []

    def test_bm25_empty_string_rejected_by_pydantic(self, app_client):
        """Empty string query must be rejected by Pydantic min_length=1 with HTTP 422."""
        resp = app_client.post(
            "/api/memory/query",
            json={"role": "bull_memory", "query": "", "top_k": 3},
        )
        assert resp.status_code == 422

    def test_bm25_nonexistent_role_online_returns_empty(self, app_client):
        """Querying a non-existent role returns empty results gracefully without raising 500."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=None):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "non_existent_role_xyz", "query": "breakout", "top_k": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "non_existent_role_xyz"
            assert data["results"] == []

    def test_bm25_nonexistent_role_offline(self, app_client):
        """When Supabase is offline, querying any role returns empty results gracefully."""
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=None):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "non_existent_role_xyz", "query": "breakout", "top_k": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["results"] == []

    def test_bm25_all_empty_documents_in_corpus(self, app_client):
        """When stored documents in DB are empty or punctuation only, BM25 fails safely and falls back."""
        empty_corpus = AgentMemoryRecord(
            role="bear_memory",
            documents=["", "   ", "???!!!"],
            recommendations=["Rec1", "Rec2", "Rec3"],
            updated_at=datetime.now(timezone.utc),
        )
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=empty_corpus):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "bear_memory", "query": "market crash", "top_k": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data["results"], list)

    def test_bm25_top_k_boundaries(self, app_client, mock_memory_corpus):
        """Verify boundary top_k values: top_k=1, top_k=20 pass; top_k=0, top_k=21, top_k=-1 return 422."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_memory_corpus):
            # top_k=1 valid
            r1 = app_client.post("/api/memory/query", json={"role": "bull_memory", "query": "NIFTY", "top_k": 1})
            assert r1.status_code == 200
            assert len(r1.json()["results"]) <= 1

            # top_k=20 valid
            r20 = app_client.post("/api/memory/query", json={"role": "bull_memory", "query": "NIFTY", "top_k": 20})
            assert r20.status_code == 200

            # top_k=0 invalid (ge=1)
            r0 = app_client.post("/api/memory/query", json={"role": "bull_memory", "query": "NIFTY", "top_k": 0})
            assert r0.status_code == 422

            # top_k=21 invalid (le=20)
            r21 = app_client.post("/api/memory/query", json={"role": "bull_memory", "query": "NIFTY", "top_k": 21})
            assert r21.status_code == 422

            # top_k=-1 invalid (ge=1)
            r_neg = app_client.post("/api/memory/query", json={"role": "bull_memory", "query": "NIFTY", "top_k": -1})
            assert r_neg.status_code == 422

    def test_bm25_sql_injection_attempt_query(self, app_client, mock_memory_corpus):
        """SQL injection attempt string is treated purely as search tokens, no error."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_memory_corpus):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "bull_memory", "query": "' OR '1'='1'; DROP TABLE trades;--", "top_k": 3},
            )
            assert resp.status_code == 200
            assert "results" in resp.json()

    def test_bm25_xss_payload_query(self, app_client, mock_memory_corpus):
        """XSS attempt string is treated purely as search tokens without script evaluation."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=mock_memory_corpus):
            resp = app_client.post(
                "/api/memory/query",
                json={"role": "bull_memory", "query": "<script>alert('xss')</script>", "top_k": 3},
            )
            assert resp.status_code == 200
            assert "results" in resp.json()

    def test_get_role_memories_nonexistent_role(self, app_client):
        """GET /api/memory/role/{role} for an unseeded role returns count=0 and empty entries."""
        mock_client = MagicMock()
        with patch("skopaq.api.memory_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.memory_router.MemoryRepository.get_by_role", return_value=None):
            resp = app_client.get("/api/memory/role/non_existent_role_123")
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "non_existent_role_123"
            assert data["entries"] == []
            assert data["count"] == 0


# ==============================================================================
# 2. TRADE SUMMARY MATH ALIGNMENT WITH PERFORMANCE METRICS
# ==============================================================================

class TestTradeSummaryMathAlignment:
    """Rigorous verification of trade stats calculations vs performance router metrics."""

    def _build_mock_client(self, rows: List[Dict[str, Any]]):
        """Create mock Supabase client returning given trade rows."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_select.execute.return_value = MagicMock(data=rows, count=len(rows))
        mock_table.select.return_value = mock_select
        mock_client.table.return_value = mock_table
        return mock_client

    def test_math_alignment_standard_mixed_trades(self, app_client):
        """Scenario: Mixed winning and losing trades."""
        rows = [
            {"pnl": 1500.0, "brokerage": 20.0, "is_paper": True},
            {"pnl": 2500.0, "brokerage": 25.0, "is_paper": True},
            {"pnl": -800.0, "brokerage": 15.0, "is_paper": True},
            {"pnl": -1200.0, "brokerage": 15.0, "is_paper": False},
        ]
        mock_client = self._build_mock_client(rows)

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            stats_resp = app_client.get("/api/trades/summary/stats")
            perf_resp = app_client.get("/api/performance/metrics")

            assert stats_resp.status_code == 200
            assert perf_resp.status_code == 200

            s = stats_resp.json()
            p = perf_resp.json()

            # Counts must align
            assert s["total_trades"] == 4
            assert p["total_trades"] == 4
            assert s["winning_trades"] == 2
            assert p["winning_trades"] == 2
            assert s["losing_trades"] == 2
            assert p["losing_trades"] == 2

            # Win rates must align: 2 wins / 4 decided = 50.0%
            assert s["win_rate"] == 50.0
            assert p["win_rate"] == 50.0

            # Gross profit and loss
            assert s["gross_profit"] == 4000.0
            assert s["gross_loss"] == 2000.0
            # Profit factor: 4000 / 2000 = 2.0
            assert s["profit_factor"] == 2.0
            assert p["profit_factor"] == 2.0

            # Realized PnL: 4000 - 2000 = 2000
            assert s["total_realized_pnl"] == 2000.0
            assert s["net_pnl"] == 2000.0 - 75.0  # minus 75 brokerage

    def test_math_alignment_all_winning_trades(self, app_client):
        """Scenario: 100% win rate; gross_loss is 0."""
        rows = [
            {"pnl": 1000.0, "brokerage": 10.0, "is_paper": True},
            {"pnl": 2000.0, "brokerage": 10.0, "is_paper": True},
            {"pnl": 500.0, "brokerage": 10.0, "is_paper": True},
        ]
        mock_client = self._build_mock_client(rows)

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            assert s["win_rate"] == 100.0
            assert p["win_rate"] == 100.0
            assert s["winning_trades"] == 3
            assert p["winning_trades"] == 3
            assert s["losing_trades"] == 0
            assert p["losing_trades"] == 0
            assert s["gross_profit"] == 3500.0
            assert s["gross_loss"] == 0.0
            # When gross_loss=0 and gross_profit>0, both routers set profit_factor = gross_profit
            assert s["profit_factor"] == 3500.0
            assert p["profit_factor"] == 3500.0

    def test_math_alignment_all_losing_trades(self, app_client):
        """Scenario: 0% win rate; gross_profit is 0."""
        rows = [
            {"pnl": -500.0, "brokerage": 10.0, "is_paper": True},
            {"pnl": -1500.0, "brokerage": 10.0, "is_paper": True},
        ]
        mock_client = self._build_mock_client(rows)

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            assert s["win_rate"] == 0.0
            assert p["win_rate"] == 0.0
            assert s["winning_trades"] == 0
            assert p["winning_trades"] == 0
            assert s["losing_trades"] == 2
            assert p["losing_trades"] == 2
            assert s["gross_profit"] == 0.0
            assert s["gross_loss"] == 2000.0
            assert s["profit_factor"] == 0.0
            assert p["profit_factor"] == 0.0

    def test_math_alignment_zero_trades(self, app_client):
        """Scenario: No trades recorded (fresh deployment)."""
        mock_client = self._build_mock_client([])

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            assert s["total_trades"] == 0
            assert p["total_trades"] == 0
            assert s["win_rate"] == 0.0
            assert p["win_rate"] == 0.0
            assert s["winning_trades"] == 0
            assert p["winning_trades"] == 0
            assert s["losing_trades"] == 0
            assert p["losing_trades"] == 0
            assert s["profit_factor"] == 1.0
            assert p["profit_factor"] == 1.0

    def test_math_alignment_scratch_trades_zero_pnl(self, app_client):
        """Scenario: Scratch trades with exact 0.0 PnL (neither win nor loss)."""
        rows = [
            {"pnl": 0.0, "brokerage": 20.0, "is_paper": True},
            {"pnl": 0.0, "brokerage": 20.0, "is_paper": True},
        ]
        mock_client = self._build_mock_client(rows)

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            assert s["total_trades"] == 2
            assert p["total_trades"] == 2
            assert s["winning_trades"] == 0
            assert p["winning_trades"] == 0
            assert s["losing_trades"] == 0
            assert p["losing_trades"] == 0
            assert s["win_rate"] == 0.0
            assert p["win_rate"] == 0.0
            assert s["gross_profit"] == 0.0
            assert s["gross_loss"] == 0.0

    def test_math_alignment_open_and_pending_trades_null_pnl(self, app_client):
        """Scenario: Open trades where pnl is None; must not distort realized counts."""
        rows = [
            {"pnl": 1200.0, "brokerage": 10.0, "is_paper": True},
            {"pnl": -400.0, "brokerage": 10.0, "is_paper": True},
            {"pnl": None, "brokerage": 0.0, "is_paper": True},  # Open trade
            {"pnl": None, "brokerage": 0.0, "is_paper": True},  # Pending trade
        ]
        mock_client = self._build_mock_client(rows)

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=mock_client):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            # Total trades counts all 4 rows
            assert s["total_trades"] == 4
            assert p["total_trades"] == 4
            # Realized win/loss counts only closed trades with non-null PnL
            assert s["winning_trades"] == 1
            assert p["winning_trades"] == 1
            assert s["losing_trades"] == 1
            assert p["losing_trades"] == 1
            assert s["win_rate"] == 50.0
            assert p["win_rate"] == 50.0
            assert s["profit_factor"] == 3.0
            assert p["profit_factor"] == 3.0

    def test_math_alignment_offline_mode(self, app_client):
        """When Supabase is completely offline, both routers return matching default null-states."""
        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=None), \
             patch("skopaq.api.performance_router.get_safe_supabase", return_value=None):

            s = app_client.get("/api/trades/summary/stats").json()
            p = app_client.get("/api/performance/metrics").json()

            assert s["total_trades"] == 0
            assert p["total_trades"] == 0
            assert s["win_rate"] == 0.0
            assert p["win_rate"] == 0.0
            assert s["profit_factor"] == 1.0
            assert p["profit_factor"] == 1.0


# ==============================================================================
# 3. UNTESTED BRANCHES & FAILURE MODES
# ==============================================================================

class TestApiUntestedBranches:
    """Target untested branches across all routers."""

    def test_trades_invalid_pagination_limits(self, app_client):
        """GET /api/trades rejects invalid limit (<1 or >500) and negative offset with 422."""
        r_zero = app_client.get("/api/trades?limit=0")
        assert r_zero.status_code == 422

        r_huge = app_client.get("/api/trades?limit=501")
        assert r_huge.status_code == 422

        r_neg_offset = app_client.get("/api/trades?offset=-1")
        assert r_neg_offset.status_code == 422

    def test_trades_invalid_uuid_returns_400(self, app_client):
        """GET /api/trades/{trade_id} with non-UUID string returns HTTP 400."""
        resp = app_client.get("/api/trades/not-a-valid-uuid-12345")
        assert resp.status_code == 400
        assert "Invalid UUID format" in resp.json()["detail"]

    def test_trades_nonexistent_uuid_returns_404(self, app_client):
        """GET /api/trades/{trade_id} with valid UUID that doesn't exist returns HTTP 404."""
        random_uuid = str(uuid4())
        mock_client = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None

        with patch("skopaq.api.trades_router.get_safe_supabase", return_value=mock_client), \
             patch("skopaq.api.trades_router.TradeRepository", return_value=mock_repo):
            resp = app_client.get(f"/api/trades/{random_uuid}")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"]

    def test_safety_simulate_invalid_payloads(self, app_client):
        """POST /api/safety/simulate rejects non-positive price and quantity with HTTP 422."""
        # Zero price
        r1 = app_client.post("/api/safety/simulate", json={"symbol": "INFY", "quantity": 10, "price": 0.0})
        assert r1.status_code == 422

        # Negative price
        r2 = app_client.post("/api/safety/simulate", json={"symbol": "INFY", "quantity": 10, "price": -100.0})
        assert r2.status_code == 422

        # Zero quantity
        r3 = app_client.post("/api/safety/simulate", json={"symbol": "INFY", "quantity": 0, "price": 100.0})
        assert r3.status_code == 422

        # Confidence out of bounds
        r4 = app_client.post("/api/safety/simulate", json={"symbol": "INFY", "quantity": 10, "price": 100.0, "confidence": 150})
        assert r4.status_code == 422

    def test_analysis_nonexistent_job_returns_404(self, app_client):
        """GET /api/analysis/{job_id} and stream endpoint return HTTP 404 for unknown job."""
        fake_id = "job_nonexistent_99999"
        r_get = app_client.get(f"/api/analysis/{fake_id}")
        assert r_get.status_code == 404

        r_stream = app_client.get(f"/api/analysis/{fake_id}/stream")
        assert r_stream.status_code == 404

    def test_system_config_masks_secrets(self, app_client):
        """GET /api/system/config returns sanitized boolean flags for services without exposing keys."""
        resp = app_client.get("/api/system/config")
        assert resp.status_code == 200
        data = resp.json()

        assert "services" in data
        services = data["services"]
        for svc_name, is_configured in services.items():
            assert isinstance(is_configured, bool), f"Service secret {svc_name} leaked raw value: {is_configured}"
