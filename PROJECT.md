# Project: NovaSwarm Trader Production-Ready Mock Eradication & Subsystem Hardening

## Architecture
NovaSwarm Trader is an autonomous AI multi-agent algorithmic trading platform for Indian equities.
This project phase executes the complete, production-ready eradication of all mock data, seed arrays, fake stats, and simulated fallbacks across all frontend pages and backend subsystems, replacing them with live subsystem integrations, a unified shared paper trading engine, real live market scanning, and clean, truthful empty states.

1. **Centralized Shared Paper Trading Engine (`novaswarm/broker/paper_engine.py`)**:
   - Single in-memory singleton via `get_shared_paper_engine()` and `reset_shared_paper_engine()`.
   - Unified synchronization of cash (₹10,00,000.00), open positions, executed orders, and realized/unrealized P&L across `server.py`, `performance_router.py`, `safety_router.py`, `chat/session.py`, and `chat/tools.py`.
2. **Hardened Live Market Scanner (`novaswarm/scanner/engine.py`)**:
   - Real batch quote fetching across NIFTY 50 via `yfinance.download` / INDstocks.
   - Real LLM screening via `instantiate_model("google", "gemini-flash-lite-latest")` evaluating against `SCREEN_PROMPT_TEMPLATE`.
   - Wired in `novaswarm/api/server.py:_get_scanner()` to power `POST /api/scanner/scan` and `GET /api/scanner/candidates`.
3. **Truthful Performance Metrics & Resilient Learning Tracker**:
   - `novaswarm/api/performance_router.py`: Strict calculation of Sharpe ratio and Max Drawdown from trade returns (0.0 if trades < 5); 0.0 accuracy and 0 predictions in `/models` when no prediction history exists.
   - `novaswarm/learning/tracker.py`: Resilient multi-tier query (Postgres -> Supabase `trades` via `get_safe_supabase()` -> in-memory) returning truthful zeroed metrics without connection exceptions.
4. **Chat Bridge Multi-Modal Text Extraction & Timeout Configuration**:
   - `novaswarm/chat/bridge.py`: Robust `_extract_text(content)` handling both strings and Google GenAI/Anthropic block lists (`[{'type': 'text', ...}]`).
   - `frontend/src/lib/api.ts`: 45-second timeout for `/api/chat/message`.
5. **Frontend Seed & Mock Data Eradication**:
   - Clean empty states across `/scanner`, `/chat`, `/trades`, `/portfolio`, `/`, `/analytics`, and `/settings`.
   - Total purge of `SEED_CANDIDATES`, `SEED_TRADES`, `SEED_SNAPSHOTS`, `SEED_MODEL_ACCURACIES`, `SEED_HEALING_EVENTS`, and `handleSimulatedResponse`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Centralized Shared Paper Engine Singleton | Implement `get_shared_paper_engine()` & rewire server, performance, safety, session, and tools | M1 | R3 |
| F2 | Truthful Performance Metrics | Remove 1.5/1.2 fallbacks, compute real Sharpe/Drawdown (0.0 if trades < 5), 0.0 model accuracy when empty | M1 | R4 |
| F3 | Resilient Learning Tracker Fallback | Safe multi-tier Supabase/in-memory fallback without throwing connection exceptions | M1 | R4 |
| F4 | Live Batch Quote Fetching | Real batch quote fetching for NIFTY 50 via yfinance/INDstocks in scanner engine | M2 | R2 |
| F5 | Live Gemini Flash Lite Scanner | Real LLM screener using `gemini-flash-lite-latest` evaluating metrics against template | M2 | R2 |
| F6 | Server Scanner Wiring & Models Enrichment | Wire `_get_scanner()` with real fetcher/screener, enrich candidate dict with metrics | M2 | R2 |
| F7 | Chat Multi-Modal Text Extraction | Implement `_extract_text(content)` handling GenAI block lists and objects | M2 | R5 |
| F8 | Scanner Page Mock Eradication | Purge `SEED_CANDIDATES`, render interactive empty state with on-demand scan action | M3 | R1 |
| F9 | Chat Page Simulated Response Removal | Delete `handleSimulatedResponse`, render truthful error card with retry | M3 | R1 |
| F10 | Trade History Truthful Empty State | Purge `SEED_TRADES` and 38-trade fallback, render 0 trades and 0% win rate | M3 | R1 |
| F11 | Portfolio Cockpit Real Cash & Empty States | Purge fake positions/holdings/orders, show ₹10,00,000 cash and empty table rows | M3 | R1 |
| F12 | Dashboard Dynamic Overview & Empty States | Purge fake positions, ₹14,250 P&L, 68.5% win rate; derive active LLMs dynamically | M3 | R1 |
| F13 | Analytics Baseline Equity & Truthful Stats | Purge `SEED_SNAPSHOTS` & `SEED_MODEL_ACCURACIES`, baseline equity ₹10,00,000, 0.0 metrics | M3 | R1 |
| F14 | Settings Dynamic Models & Empty Healing | Purge `SEED_HEALING_EVENTS` & `SEED_LLM_MODELS`, load models from `/api/system/models` | M3 | R1 |
| F15 | API Client Chat Timeout Configuration | Configure 45s timeout for chat message requests in `frontend/src/lib/api.ts` | M3 | R5 |
| F16 | Static Analysis & Live Endpoint Verification | Full verification: tsc, flake8, py_compile, live HTTP endpoint probing across all routes | M4 | AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M0 | Survey & Scope Mapping | 3 parallel Explorers mapping frontend, scanner/paper engine, and perf/chat bridge | none | DONE |
| M1 | Centralized Paper Engine & Truthful Performance/Learning | Implement `get_shared_paper_engine()` and rewire all routers; fix Sharpe/Drawdown and model accuracies; resilient learning tracker | M0 | DONE |
| M2 | Live Market Scanner Hardening & Chat Assistant Bridge | Real batch quote fetching & Gemini screener in scanner engine; wire `_get_scanner()`; `_extract_text` in chat bridge | M0 | IN_PROGRESS |
| M3 | Frontend Seed & Mock Data Elimination & Empty States | Purge all SEED_* arrays and handleSimulatedResponse across all 7 Next.js pages; increase chat timeout to 45s | M1, M2 | PLANNED |
| M4 | Comprehensive Static Analysis & Live Endpoint Probing | Verify 0 mock occurrences in frontend, clean tsc & flake8, live endpoint probes across all backend endpoints & frontend routes | M1, M2, M3 | PLANNED |

## Interface Contracts

### 1. Trades Router (`/api/trades`)
- `GET /api/trades`: Query parameters: `limit` (default 50), `offset` (default 0), `status` (open/closed/pending), `symbol` (str), `strategy` (str). Returns `{"trades": list[TradeRecord], "total": int}`.
- `GET /api/trades/{trade_id}`: Path parameter: `trade_id`. Returns single `TradeRecord` with detailed model predictions, signals, and reflection if closed.
- `GET /api/trades/summary/stats`: Returns `{"total_trades": int, "winning_trades": int, "losing_trades": int, "win_rate": float, "total_realized_pnl": float, "gross_profit": float, "gross_loss": float, "profit_factor": float}`.

### 2. Analysis Router (`/api/analysis`)
- `POST /api/analysis`: Body: `{"symbol": str, "urgency": str (optional, default "medium"), "lookback_days": int (optional, default 30)}`. Returns `{"job_id": str, "symbol": str, "status": "pending", "created_at": str}`.
- `GET /api/analysis/{job_id}`: Returns current job status and snapshot of completed agent reports, logs, and decision card.
- `GET /api/analysis/{job_id}/stream`: Server-Sent Events endpoint emitting `data: JSON\n\n` with event types:
  - `job_started`: `{"job_id": str, "symbol": str, "timestamp": str}`
  - `agent_status`: `{"agent_id": str, "team": str, "status": "pending"|"running"|"completed"|"failed", "timestamp": str}`
  - `tool_call`: `{"agent_id": str, "tool_name": str, "tool_args": dict, "tool_result": any, "timestamp": str}`
  - `agent_chunk`: `{"agent_id": str, "chunk": str, "timestamp": str}`
  - `agent_report`: `{"agent_id": str, "team": str, "report_markdown": str, "timestamp": str}`
  - `event_log`: `{"level": "INFO"|"WARNING"|"ERROR", "message": str, "timestamp": str}`
  - `decision_card`: `{"verdict": "BUY"|"SELL"|"HOLD", "confidence": int, "position_size": int, "entry_price": float, "stop_loss": float, "target": float, "risk_reward_ratio": float, "reasoning": str, "timestamp": str}`
  - `job_completed`: `{"job_id": str, "final_verdict": str, "confidence": int, "duration_seconds": float, "timestamp": str}`
  - `job_failed`: `{"job_id": str, "error": str, "timestamp": str}`
  - Keepalive ping every 15s: `: keepalive\n\n`.

### 3. Memory Router (`/api/memory`)
- `GET /api/memory/roles`: Returns list of 5 memory roles `["bull_memory", "bear_memory", "trader_memory", "invest_judge_memory", "risk_manager_memory"]`.
- `GET /api/memory/role/{role_name}`: Returns `{"role": str, "documents_count": int, "memories": list[dict]}`.
- `POST /api/memory/query`: Body `{"role": str, "query": str, "top_k": int}`. Returns matched memories with similarity scores.
- `GET /api/memory/reflections`: Query parameters: `symbol`, `limit`. Returns historical trade reflection records.

### 4. Performance Router (`/api/performance`)
- `GET /api/performance/metrics`: Returns win rate, Sharpe ratio, max drawdown, total P&L, profit factor, total trades, average trade duration.
- `GET /api/performance/daily-snapshots`: Returns daily equity curve time-series: `list[{"date": str, "equity": float, "realized_pnl": float, "unrealized_pnl": float, "drawdown_pct": float}]`.
- `GET /api/performance/models`: Returns per-model accuracy breakdown (`{"model_name": str, "total_predictions": int, "accurate_predictions": int, "accuracy_pct": float, "avg_confidence": float}`).
- `GET /api/performance/learning`: Returns strategy generation learning curve and adaptation history.

### 5. Safety Router (`/api/safety`)
- `GET /api/safety/rules`: Returns frozen `SAFETY_RULES` dictionary with descriptions, thresholds, and enforcement levels.
- `POST /api/safety/simulate`: Body `{"symbol": str, "action": "BUY"|"SELL", "quantity": int, "price": float, "stop_loss": float, "target": float}`. Returns `SafetyResult(passed: bool, rejections: list[str], warnings: list[str], risk_pct: float, max_allowed_quantity: int)`.
- `GET /api/safety/status`: Returns current intraday safety state (daily drawdown, kill-switch status, open orders count, orders per minute).

### 6. System Router (`/api/system`)
- `GET /api/system/config`: Safe sanitized configuration overview (broker mode, environment, active models, scanner intervals).
- `GET /api/system/models`: Active LLM role-to-model mappings (`bull_researcher`, `bear_researcher`, `risk_manager`, etc.).
- `GET /api/system/strategies`: List of active and archived strategy versions (`StrategyVersionRecord`).
- `GET /api/system/healing`: Log of self-healing events (`HealingEventRecord`).
- `POST /api/system/healing/log`: Manually record an external self-healing action.

## Code Layout
- Write ownership boundaries:
  - Backend Routers & Models: `novaswarm/api/trades_router.py`, `novaswarm/api/analysis_models.py`, `novaswarm/api/analysis_manager.py`, `novaswarm/api/analysis_router.py`, `novaswarm/api/memory_router.py`, `novaswarm/api/performance_router.py`, `novaswarm/api/safety_router.py`, `novaswarm/api/system_router.py`, `novaswarm/api/server.py`.
  - Backend Unit Tests: `tests/unit/api/*`, `tests/unit/llm/test_ollama.py`.
  - Frontend Workspace: `frontend/package.json`, `frontend/src/*`, `frontend/public/*`, `frontend/tailwind.config.ts`, `frontend/next.config.js`.
  - E2E Tests: `tests/e2e/*`, `tests/e2e/test_runner.py`, `TEST_INFRA.md`, `TEST_READY.md`.
  - Metadata & Tracking: `.agents/*`.
