"""Opaque-box E2E Client for NovaSwarm Trader.

Supports dual-mode execution:
- 'mock': Dispatches requests to in-process FastAPI mock ASGI server.
- 'live': Dispatches HTTP and SSE requests over network to live servers.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List, Optional
import urllib.parse

from fastapi.testclient import TestClient
import httpx

from tests.e2e.mock_server import create_mock_app

logger = logging.getLogger(__name__)


class E2EResponse:
    """Wrapper normalizing responses across testclient and httpx."""

    def __init__(self, status_code: int, content: bytes, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class E2EClient:
    """Opaque-box unified API client for NovaSwarm Trader E2E tests."""

    def __init__(
        self,
        mode: str = "mock",
        backend_url: str = "http://localhost:8000",
        frontend_url: str = "http://localhost:3000",
        timeout: float = 30.0,
    ):
        self.mode = mode.lower()
        self.backend_url = backend_url.rstrip("/")
        self.frontend_url = frontend_url.rstrip("/")
        self.timeout = timeout

        if self.mode == "mock":
            self._mock_app = create_mock_app()
            self._mock_client = TestClient(self._mock_app, raise_server_exceptions=False)
        else:
            self._live_client = httpx.Client(timeout=timeout)

    def close(self):
        if self.mode == "mock":
            self._mock_client.close()
        else:
            self._live_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ── Raw HTTP Methods ─────────────────────────────────────────────────────

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, is_frontend: bool = False) -> E2EResponse:
        if self.mode == "mock":
            resp = self._mock_client.get(path, params=params)
            return E2EResponse(resp.status_code, resp.content, dict(resp.headers))
        else:
            base = self.frontend_url if is_frontend else self.backend_url
            url = f"{base}{path}"
            resp = self._live_client.get(url, params=params)
            return E2EResponse(resp.status_code, resp.content, dict(resp.headers))

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> E2EResponse:
        if self.mode == "mock":
            resp = self._mock_client.post(path, json=json_data)
            return E2EResponse(resp.status_code, resp.content, dict(resp.headers))
        else:
            url = f"{self.backend_url}{path}"
            resp = self._live_client.post(url, json=json_data)
            return E2EResponse(resp.status_code, resp.content, dict(resp.headers))

    def stream_sse(self, path: str, max_events: int = 50) -> List[Dict[str, Any]]:
        """Stream SSE events from an endpoint and parse into list of event dicts."""
        events: List[Dict[str, Any]] = []

        if self.mode == "mock":
            with self._mock_client.stream("GET", path) as response:
                current_event = None
                current_data = []

                for line in response.iter_lines():
                    if not line:
                        if current_event and current_data:
                            raw_data = "\n".join(current_data)
                            try:
                                parsed = json.loads(raw_data)
                            except Exception:
                                parsed = raw_data
                            events.append({"event": current_event, "data": parsed})
                            if len(events) >= max_events:
                                break
                        current_event = None
                        current_data = []
                        continue

                    if line.startswith(":"):
                        # SSE comment (heartbeat)
                        events.append({"event": "comment", "data": line[1:].strip()})
                        continue

                    if line.startswith("event:"):
                        current_event = line.replace("event:", "").strip()
                    elif line.startswith("data:"):
                        current_data.append(line.replace("data:", "").strip())
        else:
            url = f"{self.backend_url}{path}"
            with httpx.stream("GET", url, timeout=self.timeout) as response:
                current_event = None
                current_data = []
                for line in response.iter_lines():
                    if not line:
                        if current_event and current_data:
                            raw_data = "\n".join(current_data)
                            try:
                                parsed = json.loads(raw_data)
                            except Exception:
                                parsed = raw_data
                            events.append({"event": current_event, "data": parsed})
                            if len(events) >= max_events:
                                break
                        current_event = None
                        current_data = []
                        continue

                    if line.startswith(":"):
                        events.append({"event": "comment", "data": line[1:].strip()})
                        continue

                    if line.startswith("event:"):
                        current_event = line.replace("event:", "").strip()
                    elif line.startswith("data:"):
                        current_data.append(line.replace("data:", "").strip())

        return events

    # ── Convenience Typed Methods ────────────────────────────────────────────

    # 1. System & Health
    def get_health(self) -> E2EResponse:
        return self.get("/health")

    def get_status(self) -> E2EResponse:
        return self.get("/api/status")

    def get_portfolio(self) -> E2EResponse:
        return self.get("/api/portfolio")

    # 2. Scanner
    def get_scanner_status(self) -> E2EResponse:
        return self.get("/api/scanner/status")

    def get_scanner_candidates(self) -> E2EResponse:
        return self.get("/api/scanner/candidates")

    def trigger_scan(self) -> E2EResponse:
        return self.post("/api/scanner/scan")

    # 3. Trades
    def list_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        is_paper: Optional[bool] = None,
        status: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> E2EResponse:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if symbol:
            params["symbol"] = symbol
        if side:
            params["side"] = side
        if is_paper is not None:
            params["is_paper"] = is_paper
        if status:
            params["status"] = status
        if strategy:
            params["strategy"] = strategy
        return self.get("/api/trades", params=params)

    def get_trade(self, trade_id: str) -> E2EResponse:
        return self.get(f"/api/trades/{trade_id}")

    def get_trade_stats(self) -> E2EResponse:
        return self.get("/api/trades/summary/stats")

    # 4. Analysis & SSE
    def start_analysis(
        self,
        symbol: str,
        urgency: str = "medium",
        lookback_days: int = 30,
        selected_analysts: Optional[List[str]] = None,
    ) -> E2EResponse:
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "urgency": urgency,
            "lookback_days": lookback_days,
        }
        if selected_analysts:
            payload["selected_analysts"] = selected_analysts
        return self.post("/api/analysis", json_data=payload)

    def get_analysis_status(self, job_id: str) -> E2EResponse:
        return self.get(f"/api/analysis/{job_id}")

    def stream_analysis(self, job_id: str, max_events: int = 50) -> List[Dict[str, Any]]:
        return self.stream_sse(f"/api/analysis/{job_id}/stream", max_events=max_events)

    # 5. Memory
    def get_memory_roles(self) -> E2EResponse:
        return self.get("/api/memory/roles")

    def get_memory_by_role(self, role: str, limit: int = 50) -> E2EResponse:
        return self.get(f"/api/memory/role/{role}", params={"limit": limit})

    def query_memory(self, role: str, query: str, top_k: int = 3) -> E2EResponse:
        return self.post("/api/memory/query", json_data={"role": role, "query": query, "top_k": top_k})

    def get_reflections(self, symbol: Optional[str] = None, limit: int = 20) -> E2EResponse:
        params: Dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self.get("/api/memory/reflections", params=params)

    # 6. Performance
    def get_performance_metrics(self) -> E2EResponse:
        return self.get("/api/performance/metrics")

    def get_daily_snapshots(
        self,
        days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> E2EResponse:
        params: Dict[str, Any] = {"days": days}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.get("/api/performance/daily-snapshots", params=params)

    def get_performance_models(self) -> E2EResponse:
        return self.get("/api/performance/models")

    def get_performance_learning(self) -> E2EResponse:
        return self.get("/api/performance/learning")

    # 7. Safety
    def get_safety_rules(self) -> E2EResponse:
        return self.get("/api/safety/rules")

    def simulate_safety(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        confidence: int = 75,
    ) -> E2EResponse:
        return self.post(
            "/api/safety/simulate",
            json_data={
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "price": price,
                "stop_loss": stop_loss,
                "target": target,
                "confidence": confidence,
            },
        )

    def get_safety_status(self) -> E2EResponse:
        return self.get("/api/safety/status")

    # 8. System
    def get_system_config(self) -> E2EResponse:
        return self.get("/api/system/config")

    def get_system_models(self) -> E2EResponse:
        return self.get("/api/system/models")

    def get_system_strategies(self) -> E2EResponse:
        return self.get("/api/system/strategies")

    def get_system_healing(self, limit: int = 50, component: Optional[str] = None) -> E2EResponse:
        params: Dict[str, Any] = {"limit": limit}
        if component:
            params["component"] = component
        return self.get("/api/system/healing", params=params)

    def log_system_healing(
        self,
        component: str,
        event_type: str,
        description: str,
        action_taken: str,
        resolved: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> E2EResponse:
        return self.post(
            "/api/system/healing/log",
            json_data={
                "component": component,
                "event_type": event_type,
                "description": description,
                "action_taken": action_taken,
                "resolved": resolved,
                "metadata": metadata or {},
            },
        )

    # 9. Chat
    def send_chat_message(self, message: str, session_id: Optional[str] = None) -> E2EResponse:
        return self.post(
            "/api/chat/message",
            json_data={"message": message, "session_id": session_id},
        )

    def call_chat_tool(
        self,
        tool: str,
        args: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> E2EResponse:
        return self.post(
            "/api/chat/tool",
            json_data={"tool": tool, "args": args or {}, "session_id": session_id},
        )

    # 10. Frontend Routes
    def get_frontend_route(self, route_path: str) -> E2EResponse:
        return self.get(route_path, is_frontend=True)
