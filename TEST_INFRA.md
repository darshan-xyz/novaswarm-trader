# NovaSwarm Trader End-to-End (E2E) Test Infrastructure & Methodology Specification

## 1. Overview & Objectives

This document establishes the authoritative testing methodology, feature inventory, reliability thresholds, and scenario catalog for the **NovaSwarm Trader Autonomous AI Algorithmic Trading Platform**.

The E2E test suite operates as an **opaque-box verification system** designed to validate the system through its observable boundaries: REST API endpoints, Server-Sent Events (SSE) data streams, conversational AI interfaces, and frontend web routes.

### Primary Goals:
1. **Opaque-Box Verification**: Exercise real HTTP endpoints and streaming protocols without relying on private implementation details.
2. **Dual-Mode Execution**: Support seamless execution against an in-process high-fidelity mock adapter (`--mode mock`) for hermetic CI/offline runs, and against live production servers (`--mode live`) for staging and deployment validation.
3. **Four-Tier Architecture**:
   - **Tier 1**: Feature Coverage (>=5 tests per feature across 8 features).
   - **Tier 2**: Boundary & Corner Cases (>=5 tests per feature across 8 features).
   - **Tier 3**: Cross-Feature Combinations (Multi-system interaction pipelines).
   - **Tier 4**: Real-World Application Scenarios (Realistic algorithmic trading lifecycles).
4. **Deterministic & Self-Contained**: Every test manages its own state and executes without side effects or order dependencies.

---

## 2. Testing Methodology

The NovaSwarm Trader E2E test framework is built upon four rigorous software testing methodologies:

### 2.1 Category-Partition Method (CPM)
For each functional area, inputs and system states are decomposed into functional categories, partitioned into distinct equivalence classes, and tested with representative values:
- **Order Sides**: `BUY`, `SELL`, invalid (`HOLD`, `UNKNOWN`).
- **Trading Modes**: `paper`, `live`.
- **Order Types**: `MARKET`, `LIMIT`.
- **Trade Statuses**: `COMPLETE`, `PENDING`, `REJECTED`, `CANCELLED`.
- **Agent Roles**: `bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`.
- **System States**: Normal market hours, after-hours, circuit-breaker tripped, clean slate.

### 2.2 Boundary Value Analysis (BVA)
Tests systematically probe the extremes of acceptable and unacceptable ranges:
- **Pagination**: `limit=0` (invalid), `limit=1` (min), `limit=50` (nominal), `limit=500` (max), `limit=501` (boundary exceed), `offset=0`, `offset=1000000` (beyond dataset).
- **Position Sizing**: Quantity `0` (invalid), `1` (min allowed share), nominal, ceiling capping max position value (₹500,000).
- **Stop-Loss Percentages**: `0%` (unprotected/rejected in live), `1.9%` (<2% min threshold -> rejected), `2.0%` (exact boundary -> accepted), `5.0%` (nominal).
- **Risk Ratios & Losses**: Max daily loss threshold (`3%`), circuit breaker tripping points.
- **BM25 Search**: `top_k=0`, `top_k=1`, `top_k=1000`, empty strings, 5,000-character multi-sentence tokens.

### 2.3 Pairwise & Orthogonal Combinations
Complex interactions between disparate subsystems are isolated and verified:
- **Analysis Swarm -> Risk Simulation**: High-confidence BUY recommendation flowing directly into ATR-based position sizing and safety validation.
- **Trade Execution -> BM25 Reflection**: Closing a trade triggering automated reflection generation and persistence into the appropriate memory store.
- **Scanner Radar -> Multi-Agent Pipeline**: Scanner detecting a candidate -> pushing into the analysis background queue -> streaming agent outputs.
- **Chat Assistant -> Subsystem Tool Calls**: Natural language queries invoking underlying tools (`get_portfolio`, `check_safety`, `get_quote`) and formatting markdown responses.

### 2.4 Workload & Operational Stress Profiles
- **Stream Reconnections**: Clients disconnecting mid-stream and reconnecting to verify event replay buffer functionality.
- **Keepalive Validation**: Ensuring idle SSE connections receive `: heartbeat\n\n` comments within the 15-second SLA window.
- **Burst Rate Limits**: Rapid sequential order requests verifying the 20-order-per-minute rate limiter.

---

## 3. Feature Inventory & API Contracts

| Feature ID | Feature Name | Core Endpoints / Routes | Verification Focus |
|---|---|---|---|
| **F1** | System Overview & Health | `GET /api/status`<br>`GET /health`<br>Route `/` | Health status of Broker, Supabase, Redis, LLMs, mode (`paper`/`live`), latency <200ms. |
| **F2** | Portfolio & Positions | `GET /api/portfolio`<br>Route `/portfolio` | Real-time cash, total value, positions value, open positions list, open orders. |
| **F3** | Market Scanner | `GET /api/scanner/status`<br>`GET /api/scanner/candidates`<br>`POST /api/scanner/scan`<br>Route `/scanner` | Scan cycle counter, candidate queue, urgency levels (`HIGH`, `NORMAL`), multi-model tags. |
| **F4** | Multi-Agent Analysis & SSE | `POST /api/analysis`<br>`GET /api/analysis/{id}`<br>`GET /api/analysis/{id}/stream`<br>Route `/analysis` | Background job queuing (202), SSE event stream (`job_started`, `agent_status`, `tool_call`, `agent_chunk`, `agent_report`, `decision_card`, `job_completed`), replay buffer. |
| **F5** | Trades History & Analytics | `GET /api/trades`<br>`GET /api/trades/{id}`<br>`GET /api/trades/summary/stats`<br>Route `/trades` | Filter by symbol, side, status; detailed trade prediction metadata; win rate and profit factor math. |
| **F6** | Interactive AI Trading Chat | `POST /api/chat/message`<br>`POST /api/chat/tool`<br>Route `/chat` | Conversational response, session continuity, tool execution (`get_portfolio`, `check_safety`), structured tool call payloads. |
| **F7** | Performance Analytics | `GET /api/performance/metrics`<br>`GET /api/performance/daily-snapshots`<br>`GET /api/performance/models`<br>`GET /api/performance/learning`<br>Route `/analytics` | Sharpe ratio, max drawdown, equity time series, per-model prediction accuracy breakdown, learning curve. |
| **F8** | Settings, Health & Risk | `GET /api/system/config`<br>`GET /api/system/models`<br>`GET /api/system/healing`<br>`GET /api/system/strategies`<br>`POST /api/system/healing/log`<br>`GET /api/safety/rules`<br>`POST /api/safety/simulate`<br>`GET /api/safety/status`<br>Route `/settings` | Secret key masking, Strategy DNA versions, frozen risk rule evaluation, pre-trade simulation results, self-healing event logging. |
| **F9** | Frontend Web Routes | `GET /`<br>`GET /portfolio`<br>`GET /scanner`<br>`GET /analysis`<br>`GET /trades`<br>`GET /chat`<br>`GET /analytics`<br>`GET /settings` | Clean HTTP 200 responses for all 8 application views with correct document headers. |

---

## 4. Reliability & Performance Thresholds

| Metric | Target SLA | Failure Threshold | Action on Violation |
|---|---|---|---|
| **Health / Status Endpoints** | < 100 ms | > 500 ms | Flag high server load or blocked event loop |
| **Data Query Endpoints** (`trades`, `portfolio`) | < 250 ms | > 1,500 ms | Flag database query degradation |
| **SSE Stream First Byte (TTFB)** | < 300 ms | > 2,000 ms | Flag worker thread pool starvation |
| **SSE Keepalive Heartbeat** | 15.0 s ± 1.0 s | > 20.0 s | Client proxy connection drop alert |
| **Chat Assistant Turnaround** | < 2,500 ms | > 10,000 ms | Flag LLM rate limit or connection stall |
| **Safety Simulation Evaluation** | < 50 ms | > 200 ms | Flag synchronous check blocking |
| **Secret Masking Guarantee** | 100% masked | Any key substring > 4 chars | Immediate security audit failure |
| **Test Suite Execution Time (Mock)** | < 15.0 s total | > 60.0 s total | Optimize test runner execution |

---

## 5. Test Suite Tier Structure

### Tier 1: Feature Coverage (>=5 Tests per Feature)
- **1. Trades (6 tests)**: Default listing, symbol filtering, side filtering, single trade retrieval, summary statistics math, empty result handling.
- **2. Analysis & SSE (6 tests)**: Job creation (202), status polling, SSE `job_started`, agent reports stream, decision card generation, terminal `job_completed`.
- **3. Memory (5 tests)**: Canonical 5 roles listing, role document retrieval, BM25 semantic query, reflections query by symbol, reflections limit filtering.
- **4. Performance (5 tests)**: Metrics retrieval (Sharpe, win rate, P&L), chronological daily snapshots, date range filtering, per-model accuracy, strategy learning insights.
- **5. Safety (5 tests)**: Frozen safety rules retrieval, compliant trade pass, oversized trade rejection, stop-loss threshold violation, intraday status.
- **6. System (5 tests)**: Secret key masking, LLM model mappings, Strategy DNA history, self-healing event retrieval, manual healing event logging.
- **7. Chat (5 tests)**: Message turnaround, session continuity, direct tool execution, automated tool call payload generation, status query tool.
- **8. Frontend Routes (8 tests)**: Clean HTTP 200 rendering for all 8 application views.

### Tier 2: Boundary & Corner Cases (>=5 Tests per Feature)
- **1. Trades Boundaries (5 tests)**: 404 on missing trade ID, extreme offset pagination, invalid limit parameter (422), malformed symbol query, division-by-zero protection on zero trades.
- **2. Analysis Boundaries (5 tests)**: 404 on unknown job ID, invalid symbol payload (422), negative lookback days, concurrent stream subscriptions, late-joiner replay on finished job.
- **3. Memory Boundaries (5 tests)**: 404 on unknown role, empty query string, extreme top_k boundaries (0 and 1000), unrecorded symbol reflection search, extreme long query string.
- **4. Performance Boundaries (5 tests)**: Malformed date format (422), inverted date ranges, zero days query, zero trades portfolio calculations, extreme precision floats.
- **5. Safety Boundaries (5 tests)**: Zero quantity trade rejection, negative price handling, inverted stop-loss, order value exceeding ₹500,000 cap, rapid-fire rate limit simulation.
- **6. System Boundaries (5 tests)**: Healing log missing required fields, massive metadata payload handling, strict secret token masking validation, empty strategy history handling, unknown component query.
- **7. Chat Boundaries (5 tests)**: Empty message body (422), unknown tool execution (400), 10,000-character stress payload, malformed tool arguments, expired session handling.
- **8. Frontend Boundaries (5 tests)**: 404 on unknown route, XSS injection query sanitization, invalid pagination queries, malformed analytics range, rapid route switching.

### Tier 3: Cross-Feature Combinations (6 Pipelines)
- **T3.1**: Analysis -> Decision Card -> Safety Pre-Trade Simulation -> Order Sizing Verification.
- **T3.2**: Market Scanner Candidate -> Trigger Analysis Job -> Stream Verification -> Trade Signal Generation.
- **T3.3**: Trade Execution (Paper) -> Trade Logging (`/api/trades`) -> Memory Reflection Creation (`/api/memory/reflections`) -> BM25 Recall.
- **T3.4**: Chat Assistant `analyze_stock` Tool Call -> Analysis Job Invocations -> Trade History Query.
- **T3.5**: Daily Trade Closure -> Performance Snapshots Update (`/api/performance/daily-snapshots`) -> Model Accuracy Update (`/api/performance/models`).
- **T3.6**: Safety Rejection Event -> System Self-Healing Log Entry (`/api/system/healing`) -> System Health Alert.

### Tier 4: Real-World Application Scenarios (5 Scenarios)
- **T4.1**: The Complete Profitable Breakout Trading Lifecycle (Scan -> Debate -> Buy -> Sizing -> Safety Pass -> Fill -> Profit Target -> Close -> Reflection -> Metrics).
- **T4.2**: High-Risk Protection & Circuit Breaker Enforcement Workflow (Aggressive signal -> Over-allocation rejection -> Sector concentration rejection -> Healing audit log -> Chat explanation).
- **T4.3**: Multi-Model Swarm Disagreement & Consensus Resolution (Divergent analyst views -> Risk judge uncertainty -> Low confidence / HOLD verdict -> Zero orders).
- **T4.4**: Network Interruption & Late-Joiner Reconnection During Active Multi-Agent Run (Job launch -> Client drop -> Reconnection -> Replay buffer -> Completion).
- **T4.5**: Market Regime Shift & Strategy Adaptation Workflow (Volatile trades -> Drawdown tracking -> Strategy DNA iteration -> Memory update).

---

## 6. Execution Architecture: Mock vs Live

The test runner utilizes an abstract client interface `E2EClient`:

```
                    ┌────────────────────────────┐
                    │      tests/e2e tests       │
                    │   (Tiers 1, 2, 3, and 4)   │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
                    ┌────────────────────────────┐
                    │     E2EClient Facade       │
                    │ (Uniform Request / Stream) │
                    └─────────────┬──────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
   [--mode mock]                                     [--mode live]
         ▼                                                 ▼
┌────────────────────────────┐               ┌────────────────────────────┐
│   MockNovaSwarmServer (ASGI)  │               │   Live FastAPI Backend     │
│   In-process high-fidelity │               │   (http://localhost:8000)  │
│   router & simulator       │               │   Live Next.js Frontend    │
│                            │               │   (http://localhost:3000)  │
└────────────────────────────┘               └────────────────────────────┘
```

1. **`--mode mock` (Default)**:
   - Uses an in-process mock ASGI engine implementing all route contracts, SSE event streaming, memory indexing, risk checking, and HTML routes.
   - Requires zero external network calls, zero API keys, and runs in seconds.
   - Guaranteed deterministic execution in CI.

2. **`--mode live`**:
   - Dispatches real HTTP/HTTPS and SSE requests to the running backend (`http://localhost:8000`) and frontend (`http://localhost:3000`).
   - Validates live integration between components.

---

## 7. Test Runner Command-Line Specification

The test suite can be run directly via python:

```bash
# Run all tiers in mock mode
python tests/e2e/test_runner.py --mode mock

# Run specific tier
python tests/e2e/test_runner.py --mode mock --tier 1
python tests/e2e/test_runner.py --mode mock --tier 3

# Run specific feature tests
python tests/e2e/test_runner.py --mode mock --feature trades
python tests/e2e/test_runner.py --mode mock --feature analysis

# Run against live server
python tests/e2e/test_runner.py --mode live --backend-url http://localhost:8000

# Export JSON report
python tests/e2e/test_runner.py --mode mock --json-report test_results.json
```

Or via pytest:
```bash
python -m pytest tests/e2e/ -v
```

Exit Code Behavior:
- `0`: All tests passed cleanly.
- `1`: One or more test assertions failed or errored.
