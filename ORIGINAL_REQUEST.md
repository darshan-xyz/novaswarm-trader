# Original User Request

## 2026-09-23T07:05:10Z

Build a production-grade, enterprise-ready web UI interface and backend API expansion for SkopaqTrader, an AI multi-agent algorithmic trading platform for Indian equities.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

## Requirements

### R1. Web Dashboard & Trading Interface
Implement a full-featured, responsive dark-themed Next.js (App Router, Tailwind CSS, TypeScript) web application covering:
- **System Overview Dashboard**: Live health monitor for Broker (INDstocks/Paper), Supabase, Redis, LLM models, and portfolio KPIs.
- **Portfolio & Open Positions**: Real-time view of funds, cash, open positions with live P&L, holdings, and today's orders.
- **Market Scanner View**: Scanner status, on-demand scan triggers, and a candidate grid with urgency indicators, multi-model source tags (Technicals, News, Social), and reasoning.
- **Multi-Agent Analysis View**: Input symbol, trigger analysis, and stream live agent progress in real-time via Server-Sent Events (SSE). Display agent teams (Analyst Team, Research Team, Trading Team, Risk Management, Portfolio Management) with status badges/spinners, streaming markdown reports, event log, and the final decision card with confidence score and position sizing.
- **Trades History**: Filterable and sortable log of all past paper/live trades with expandable detail views for agent decisions, model predictions, entry/exit rationale, and realized P&L.
- **Interactive AI Trading Chat**: Web-based conversational trading assistant with tool call visibility, session continuity, and quick-action prompts.
- **Performance Analytics**: Visual equity curves, daily P&L charts (using Recharts), key metrics (win rate, max drawdown, Sharpe), and per-model prediction accuracy breakdown.
- **Settings & System Health**: Strategy DNA history, LLM model-to-role mappings, configuration viewer, and infrastructure self-healing event logs.
- Single-user local deployment without authentication barriers.

### R2. Backend API Expansion
Extend the FastAPI application with clean, modular routers (without modifying existing core trading engine or daemon logic):
- `skopaq/api/trades_router.py`: Trade queries, filtering, and summary statistics.
- `skopaq/api/analysis_router.py`: Background job runner for multi-agent graph propagation and an SSE streaming endpoint (`/api/analysis/{job_id}/stream`) emitting granular agent progress events.
- `skopaq/api/memory_router.py`: Access to agent BM25 memory stores and trade reflection searches.
- `skopaq/api/performance_router.py`: Aggregated metrics, daily snapshots, and model prediction stats.
- `skopaq/api/safety_router.py`: Pre-trade safety simulation endpoint against active risk rules.
- `skopaq/api/system_router.py`: Configuration overview, model mappings, and healing events.

### R3. Architectural Integrity & Robustness
- Build reusable UI primitives (cards, tables, buttons, badges, modals, tabs, stat cards).
- Provide typed API client utilities with standard error handling, loading states, and SSE hooks.
- Preserve backward compatibility with all existing CLI commands, MCP tools, and daemon processes.

## Acceptance Criteria

### Verification & Testing
- [ ] Backend test suite (`python -m pytest tests/unit/ -x -q`) passes with zero failures.
- [ ] Frontend builds cleanly (`npm run build` in `frontend/`) with no TypeScript or lint compilation errors.
- [ ] Backend server boots cleanly (`python -m skopaq.cli.main serve`) and all new REST endpoints return HTTP 200 with valid schemas.
- [ ] Frontend dev server boots cleanly (`npm run dev`) and every route renders without uncaught client-side console errors.
- [ ] Initiating stock analysis triggers the multi-agent graph and streams progress events over SSE until completion.
- [ ] Chat interface successfully communicates with `/api/chat/message` and renders conversational responses with tool calls.
- [ ] Trade history properly displays records queried from the Supabase database.

## 2026-09-27T05:35:15Z

Complete clean-room redesign and refactoring of SkopaqTrader to completely decouple from upstream repositories, eliminating any trace of copied code or AST similarity while guaranteeing zero functional regression across all trading, API, CLI, and frontend systems.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

## Requirements

### R1. Complete Clean-Room Upstream Decoupling
Completely purge and delete all vendored upstream directories (`tradingagents/`, `cli/`, `dataflows/`) and the root `main.py`. Re-implement all required multi-agent intelligence, quantitative indicators, market data retrieval, and episodic memory natively within `skopaq/`.

### R2. Pure-Python Async Orchestrator (LangGraph Elimination)
Replace LangGraph `StateGraph`, `MessagesState`, `ToolNode`, and custom channel reducers with a native Python async/await orchestrator (`NovaPipeline`). Implement parallel analyst execution via `asyncio.gather`, deterministic bounded loops for the adversarial debate and risk committee, and native async generator streaming for SSE and the Next.js UI.

### R3. AST & Code Plagiarism Immunity (Patent & Copyright Defense)
Ensure zero AST similarity, token-hash overlap, or structural fingerprinting with upstream code:
- Rename and re-engineer every class, method, function signature, state key, and config dictionary entry.
- Completely rewrite every single agent system prompt (all 16 roles) with new vocabulary, professional tone, distinct sentence structures, and custom markdown formatting instructions.
- Replace `stockstats` and vendor routing with pure, vectorized NumPy/Pandas mathematical formulas in `skopaq/indicators/`.
- Replace `FinancialSituationMemory` with a proprietary BM25 + recency-weighted store (`EpisodicLessonStore`).
- Replace `tradingagents.llm_clients` with a native multi-provider LLM gateway (`instantiate_model`).

### R4. Zero Functional Regression & Seamless Adapter
Preserve 100% backward compatibility for all existing surfaces:
- Provide a drop-in adapter (`SkopaqTradingGraph`) so existing execution pipelines, daemons, and session bridges work without changes.
- Ensure all CLI commands (`skopaq analyze`, `trade`, `daemon`, `scan`, `chat`, `serve`), FastAPI REST/SSE endpoints, Next.js UI dashboards, and broker execution flows continue operating identically or better.

### R5. Comprehensive Line-by-Line Automated Audit & Verification
Create an automated static and dynamic audit tool (`tools/audit_codebase.py`) that systematically scans every file and line in the codebase to verify:
- Zero remaining upstream symbols, files, or strings.
- Complete import resolution and absence of circular dependencies.
- AST syntax validity and proper error handling.
- Full execution and passage of the entire test suite and frontend production build.

## Acceptance Criteria

### Decoupling & Clean-Room Verification
- [ ] Upstream directories `tradingagents/`, `cli/`, `dataflows/` are completely removed.
- [ ] `pyproject.toml` has `tradingagents` script entry, `stockstats`, and `langgraph` removed, and package discovery points strictly to `skopaq*`.
- [ ] Root `main.py` is replaced with a clean Skopaq launcher without upstream imports.
- [ ] Recursive repository scan confirms 0 occurrences of `tradingagents`, `TradingAgentsGraph`, `route_to_vendor`, `FinancialSituationMemory`, or `stockstats` in source code.
- [ ] All agent prompts are verified as original rewrites with 0% sentence-level duplication.

### Functional & Algorithmic Parity
- [ ] Native async multi-agent pipeline executes end-to-end (Stage 1 Analysts → Stage 2 Thesis Debate → Stage 3 Order Strategy → Stage 4 Risk Committee → Stage 5 Chief Risk Officer adjudication).
- [ ] Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Supertrend, VWMA) compute accurately using pure NumPy/Pandas math.
- [ ] Unified data pipeline retrieves quotes, historical OHLCV, and fundamentals via INDstocks and yfinance fallback.
- [ ] BM25 episodic memory persists to Supabase and restores lessons seamlessly across sessions.

### Build & Test Verification
- [ ] Automated verification script `tools/audit_codebase.py` runs and passes with zero warnings or errors.
- [ ] Backend unit test suite (`python -m pytest tests/unit/ -q`) passes 100% with all 605+ tests green.
- [ ] Integration tests pass cleanly.
- [ ] Next.js frontend builds without errors (`npm run build` in `frontend/`) with 0 TypeScript and 0 lint errors.
- [ ] CLI smoke tests (`python -m skopaq.cli.main --help`, `status`, `version`) execute with exit code 0.

## 2026-09-27T06:01:58Z

Complete clean-room redesign and refactoring of SkopaqTrader to completely decouple from upstream repositories, eliminating any trace of copied code or AST similarity while guaranteeing zero functional regression across all trading, API, CLI, and frontend systems.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

Note on existing state: Phase 0 (Survey & Scope Mapping) is ALREADY COMPLETED and documented in `.agents/teamwork/orchestrator_1/PROJECT.md` and `.agents/teamwork/orchestrator_1/TEST_INFRA.md`. Continue directly from Milestone 1 (Quantitative Indicators & Market Data Pipeline) through Milestone 6.

## Requirements

### R1. Complete Clean-Room Upstream Decoupling
Completely purge and delete all vendored upstream directories (`tradingagents/`, `cli/`, `dataflows/`) and the root `main.py`. Re-implement all required multi-agent intelligence, quantitative indicators, market data retrieval, and episodic memory natively within `skopaq/`.

### R2. Pure-Python Async Orchestrator (LangGraph Elimination)
Replace LangGraph `StateGraph`, `MessagesState`, `ToolNode`, and custom channel reducers with a native Python async/await orchestrator (`NovaPipeline`). Implement parallel analyst execution via `asyncio.gather`, deterministic bounded loops for the adversarial debate and risk committee, and native async generator streaming for SSE and the Next.js UI.

### R3. AST & Code Plagiarism Immunity (Patent & Copyright Defense)
Ensure zero AST similarity, token-hash overlap, or structural fingerprinting with upstream code:
- Rename and re-engineer every class, method, function signature, state key, and config dictionary entry.
- Completely rewrite every single agent system prompt (all 16 roles) with new vocabulary, professional tone, distinct sentence structures, and custom markdown formatting instructions.
- Replace `stockstats` and vendor routing with pure, vectorized NumPy/Pandas mathematical formulas in `skopaq/indicators/`.
- Replace `FinancialSituationMemory` with a proprietary BM25 + recency-weighted store (`EpisodicLessonStore`).
- Replace `tradingagents.llm_clients` with a native multi-provider LLM gateway (`instantiate_model`).

### R4. Zero Functional Regression & Seamless Adapter
Preserve 100% backward compatibility for all existing surfaces:
- Provide a drop-in adapter (`SkopaqTradingGraph`) so existing execution pipelines, daemons, and session bridges work without changes.
- Ensure all CLI commands (`skopaq analyze`, `trade`, `daemon`, `scan`, `chat`, `serve`), FastAPI REST/SSE endpoints, Next.js UI dashboards, and broker execution flows continue operating identically or better.

### R5. Comprehensive Line-by-Line Automated Audit & Verification
Create an automated static and dynamic audit tool (`tools/audit_codebase.py`) that systematically scans every file and line in the codebase to verify:
- Zero remaining upstream symbols, files, or strings.
- Complete import resolution and absence of circular dependencies.
- AST syntax validity and proper error handling.
- Full execution and passage of the entire test suite and frontend production build.

## Acceptance Criteria

### Decoupling & Clean-Room Verification
- [ ] Upstream directories `tradingagents/`, `cli/`, `dataflows/` are completely removed.
- [ ] `pyproject.toml` has `tradingagents` script entry, `stockstats`, and `langgraph` removed, and package discovery points strictly to `skopaq*`.
- [ ] Root `main.py` is replaced with a clean Skopaq launcher without upstream imports.
- [ ] Recursive repository scan confirms 0 occurrences of `tradingagents`, `TradingAgentsGraph`, `route_to_vendor`, `FinancialSituationMemory`, or `stockstats` in source code.
- [ ] All agent prompts are verified as original rewrites with 0% sentence-level duplication.

### Functional & Algorithmic Parity
- [ ] Native async multi-agent pipeline executes end-to-end (Stage 1 Analysts → Stage 2 Thesis Debate → Stage 3 Order Strategy → Stage 4 Risk Committee → Stage 5 Chief Risk Officer adjudication).
- [ ] Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Supertrend, VWMA) compute accurately using pure NumPy/Pandas math.
- [ ] Unified data pipeline retrieves quotes, historical OHLCV, and fundamentals via INDstocks and yfinance fallback.
- [ ] BM25 episodic memory persists to Supabase and restores lessons seamlessly across sessions.

### Build & Test Verification
- [ ] Automated verification script `tools/audit_codebase.py` runs and passes with zero warnings or errors.
- [ ] Backend unit test suite (`python -m pytest tests/unit/ -q`) passes 100% with all 605+ tests green.
- [ ] Integration tests pass cleanly.
- [ ] Next.js frontend builds without errors (`npm run build` in `frontend/`) with 0 TypeScript and 0 lint errors.
- [ ] CLI smoke tests (`python -m skopaq.cli.main --help`, `status`, `version`) execute with exit code 0.

## 2026-09-27T06:48:25Z

Complete clean-room redesign and refactoring of SkopaqTrader to completely decouple from upstream repositories, eliminating any trace of copied code or AST similarity while guaranteeing zero functional regression across all trading, API, CLI, and frontend systems.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

Note on existing state: Phase 0 (Survey) and Milestone 1 (Quantitative Indicators & Market Data Pipeline) are ALREADY COMPLETED, implemented, and verified on disk in `skopaq/indicators/` and `skopaq/data/` (all 761 unit tests passing). Continue directly from Milestone 2 (Multi-Provider LLM Gateway & Proprietary Episodic Memory) through Milestone 6.

## Requirements

### R1. Complete Clean-Room Upstream Decoupling
Completely purge and delete all vendored upstream directories (`tradingagents/`, `cli/`, `dataflows/`) and the root `main.py`. Re-implement all required multi-agent intelligence, quantitative indicators, market data retrieval, and episodic memory natively within `skopaq/`.

### R2. Pure-Python Async Orchestrator (LangGraph Elimination)
Replace LangGraph `StateGraph`, `MessagesState`, `ToolNode`, and custom channel reducers with a native Python async/await orchestrator (`NovaPipeline`). Implement parallel analyst execution via `asyncio.gather`, deterministic bounded loops for the adversarial debate and risk committee, and native async generator streaming for SSE and the Next.js UI.

### R3. AST & Code Plagiarism Immunity (Patent & Copyright Defense)
Ensure zero AST similarity, token-hash overlap, or structural fingerprinting with upstream code:
- Rename and re-engineer every class, method, function signature, state key, and config dictionary entry.
- Completely rewrite every single agent system prompt (all 16 roles) with new vocabulary, professional tone, distinct sentence structures, and custom markdown formatting instructions.
- Replace `stockstats` and vendor routing with pure, vectorized NumPy/Pandas mathematical formulas in `skopaq/indicators/` (Completed in M1).
- Replace `FinancialSituationMemory` with a proprietary BM25 + recency-weighted store (`EpisodicLessonStore`) in `skopaq/memory/episodic.py`.
- Replace `tradingagents.llm_clients` with a native multi-provider LLM gateway (`instantiate_model`) in `skopaq/llm/client_factory.py`.

### R4. Zero Functional Regression & Seamless Adapter
Preserve 100% backward compatibility for all existing surfaces:
- Provide a drop-in adapter (`SkopaqTradingGraph`) so existing execution pipelines, daemons, and session bridges work without changes.
- Ensure all CLI commands (`skopaq analyze`, `trade`, `daemon`, `scan`, `chat`, `serve`), FastAPI REST/SSE endpoints, Next.js UI dashboards, and broker execution flows continue operating identically or better.

### R5. Comprehensive Line-by-Line Automated Audit & Verification
Create an automated static and dynamic audit tool (`tools/audit_codebase.py`) that systematically scans every file and line in the codebase to verify:
- Zero remaining upstream symbols, files, or strings.
- Complete import resolution and absence of circular dependencies.
- AST syntax validity and proper error handling.
- Full execution and passage of the entire test suite and frontend production build.

## Acceptance Criteria

### Decoupling & Clean-Room Verification
- [ ] Upstream directories `tradingagents/`, `cli/`, `dataflows/` are completely removed.
- [ ] `pyproject.toml` has `tradingagents` script entry, `stockstats`, and `langgraph` removed, and package discovery points strictly to `skopaq*`.
- [ ] Root `main.py` is replaced with a clean Skopaq launcher without upstream imports.
- [ ] Recursive repository scan confirms 0 occurrences of `tradingagents`, `TradingAgentsGraph`, `route_to_vendor`, `FinancialSituationMemory`, or `stockstats` in source code.
- [ ] All agent prompts are verified as original rewrites with 0% sentence-level duplication.

### Functional & Algorithmic Parity
- [ ] Native async multi-agent pipeline executes end-to-end (Stage 1 Analysts → Stage 2 Thesis Debate → Stage 3 Order Strategy → Stage 4 Risk Committee → Stage 5 Chief Risk Officer adjudication).
- [ ] Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Supertrend, VWMA) compute accurately using pure NumPy/Pandas math (Verified: 154 M1 tests pass).
- [ ] Unified data pipeline retrieves quotes, historical OHLCV, and fundamentals via INDstocks and yfinance fallback (Verified in M1).
- [ ] BM25 episodic memory persists to Supabase and restores lessons seamlessly across sessions.

### Build & Test Verification
- [ ] Automated verification script `tools/audit_codebase.py` runs and passes with zero warnings or errors.
- [ ] Backend unit test suite (`python -m pytest tests/unit/ -q`) passes 100% with all 761+ tests green.
- [ ] Integration tests pass cleanly.
- [ ] Next.js frontend builds without errors (`npm run build` in `frontend/`) with 0 TypeScript and 0 lint errors.
- [ ] CLI smoke tests (`python -m skopaq.cli.main --help`, `status`, `version`) execute with exit code 0.

## 2026-09-27T13:32:57Z

Complete clean-room redesign and refactoring of SkopaqTrader to completely decouple from upstream repositories, eliminating any trace of copied code or AST similarity while guaranteeing zero functional regression across all trading, API, CLI, and frontend systems.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

Note on existing state: Phase 0 (Survey), Milestone 1 (Quantitative Indicators & Market Data Pipeline), and Milestone 2 (Multi-Provider LLM Gateway & Proprietary Episodic Memory) are ALREADY COMPLETED, implemented, and verified on disk in `skopaq/indicators/`, `skopaq/data/`, `skopaq/llm/`, and `skopaq/memory/episodic.py` with all unit and stress tests passing (154 M1 tests + 152 M2 tests pass). Continue directly from Milestone 3 (Pure-Python Async Orchestrator NovaPipeline & 16 Rewritten Agent Prompts) through Milestone 6.

## Requirements

### R1. Pure-Python Async Orchestrator (LangGraph Elimination)
Implement `skopaq/orchestration/`:
- `context.py`: Strongly-typed Pydantic V2 state models (`AnalysisContext`, `ThesisDebateContext`, `RiskDeliberationContext`) replacing `AgentState` TypedDict and MessagesState.
- `engine.py`: `NovaPipeline` - native Python async/await orchestrator replacing LangGraph `StateGraph`, `ToolNode`, and custom reducers. Parallel analyst execution via `asyncio.gather`, deterministic bounded loops for the adversarial debate and risk committee, and native async generator streaming for SSE and the Next.js UI.
- `reflection.py`: `PostTradeReflector` replacing upstream reflector.
- `signal_extraction.py`: `DecisionExtractor` replacing upstream signal processor.

### R2. 16 Clean-Room Rewritten Agent Prompts & Intelligence Modules
Implement `skopaq/intelligence/`:
- Completely rewrite all 16 agent system prompts with new vocabulary, professional tone, distinct sentence structures, and custom markdown formatting instructions.
- Zero sentence-level or structural duplication with upstream prompts.
- Submodules:
  - `skopaq/intelligence/analysts/`: `technical.py`, `sentiment.py`, `macro.py`, `valuation.py`, `network.py`, `tokenomics.py`, `derivatives.py`
  - `skopaq/intelligence/debate/`: `advocate.py` (Upside & Downside advocates), `adjudicator.py` (Thesis Adjudicator)
  - `skopaq/intelligence/risk_committee/`: `perspectives.py` (Growth, Preservation, Balanced perspectives), `chief_risk.py` (Chief Risk Officer)
  - `skopaq/intelligence/execution/`: `order_strategist.py`

### R3. Backward-Compatible Adapter & System Integration (Milestone 4)
- Rewire `skopaq/graph/skopaq_graph.py` as a drop-in adapter (`SkopaqTradingGraph`) around `NovaPipeline`.
- Rewire all remaining upstream import sites in `skopaq/`:
  - `skopaq/agents/sell_analyst.py`
  - `skopaq/risk/atr.py`
  - `skopaq/mcp_server.py`
  - `skopaq/backtest/evolve.py`
  - `skopaq/chat/session.py`
  - `skopaq/cli/main.py`
  - `skopaq/cli/display.py`
  - `tests/integration/test_crypto_data_apis.py`
  - `tests/integration/test_indstocks.py`

### R4. Complete Upstream Purge & Package Cleanup (Milestone 5)
- Completely delete vendored upstream directories: `tradingagents/`, `cli/`, `dataflows/`.
- Replace root `main.py` with a clean Skopaq launcher.
- Clean `pyproject.toml` (remove `tradingagents` script entry, `stockstats`, `langgraph`, and fix package discovery).

### R5. Comprehensive Line-by-Line Automated Audit & Verification (Milestone 6)
Create `tools/audit_codebase.py` and verify:
- Zero remaining upstream symbols, files, or strings across the entire codebase.
- Complete import resolution and absence of circular dependencies.
- AST syntax validity and proper error handling across all files.
- Full execution and passage of the entire test suite (all unit + integration tests green).
- Clean Next.js frontend production build (`npm run build` in `frontend/`).
- CLI smoke tests execute with exit code 0.

## Acceptance Criteria

### Decoupling & Clean-Room Verification
- [ ] Upstream directories `tradingagents/`, `cli/`, `dataflows/` are completely removed.
- [ ] `pyproject.toml` has `tradingagents` script entry, `stockstats`, and `langgraph` removed, and package discovery points strictly to `skopaq*`.
- [ ] Root `main.py` is replaced with a clean Skopaq launcher without upstream imports.
- [ ] Recursive repository scan confirms 0 occurrences of `tradingagents`, `TradingAgentsGraph`, `route_to_vendor`, `FinancialSituationMemory`, or `stockstats` in source code.
- [ ] All agent prompts are verified as original rewrites with 0% sentence-level duplication.

### Functional & Algorithmic Parity
- [ ] Native async multi-agent pipeline (`NovaPipeline`) executes end-to-end (Stage 1 Analysts → Stage 2 Thesis Debate → Stage 3 Order Strategy → Stage 4 Risk Committee → Stage 5 Chief Risk Officer adjudication).
- [ ] Technical indicators compute accurately using pure NumPy/Pandas math (Verified: 154 M1 tests pass).
- [ ] Unified data pipeline retrieves quotes, historical OHLCV, and fundamentals via INDstocks and yfinance fallback (Verified in M1).
- [ ] BM25 episodic memory persists to Supabase and restores lessons seamlessly across sessions (Verified in M2).
- [ ] Backward-compatible adapter allows all CLI commands (`skopaq analyze`, `trade`, `daemon`, etc.) to run without modification.

### Build & Test Verification
- [ ] Automated verification script `tools/audit_codebase.py` runs and passes with zero warnings or errors.
- [ ] Backend unit test suite passes 100% with all unit tests green.
- [ ] Integration tests pass cleanly.
- [ ] Next.js frontend builds without errors (`npm run build` in `frontend/`) with 0 TypeScript and 0 lint errors.
- [ ] CLI smoke tests (`python -m skopaq.cli.main --help`, `status`, `version`) execute with exit code 0.

## 2026-10-01T11:02:20Z

Complete production-ready eradication of all mock data, seed arrays, fake stats, and simulated fallbacks across all frontend pages and backend subsystems of SkopaqTrader, replacing them with live subsystem integrations, a unified shared paper trading engine, real live market scanning, and clean, truthful empty states.

Working directory: d:/projects/skopaqtrader-main
Integrity mode: development

CRITICAL CONSTRAINT: NEVER execute or use any test runner in the project (do NOT run pytest, unittest, or tools/audit_codebase.py). Verification must be strictly performed via static analysis (py_compile, flake8, tsc --noEmit) and live endpoint probing.

## Requirements

### R1. Frontend Seed & Mock Data Elimination
Purge all client-side fake data, hardcoded seed arrays, and simulated fallbacks across the entire Next.js application:
- **Market Scanner (`frontend/src/app/scanner/page.tsx`)**: Delete `SEED_CANDIDATES` array. Render a clean empty state with on-demand scan action when no candidates are present.
- **Interactive AI Chat (`frontend/src/app/chat/page.tsx`)**: Completely remove `handleSimulatedResponse`. When backend fails, display a truthful error message with retry rather than fabricating fake portfolio snapshots or scans.
- **Trade History (`frontend/src/app/trades/page.tsx`)**: Delete `SEED_TRADES` array and hardcoded 38-trade fallback summary stats. Show 0 trades and 0% win rate when DB is empty.
- **Portfolio Cockpit (`frontend/src/app/portfolio/page.tsx`)**: Remove fake fallback positions (RELIANCE, TCS, INFY), holdings, and orders arrays. Show real cash (₹10,00,000.00) and truthful empty states.
- **System Overview Dashboard (`frontend/src/app/page.tsx`)**: Remove fake positions fallback, hardcoded ₹14,250 P&L, and 68.5% win rate. Derive active LLMs dynamically from backend status.
- **Analytics (`frontend/src/app/analytics/page.tsx`)**: Delete `SEED_SNAPSHOTS` and `SEED_MODEL_ACCURACIES`. Display baseline equity at initial capital and 0.0 metrics when trade history is empty.
- **Settings (`frontend/src/app/settings/page.tsx`)**: Delete `SEED_HEALING_EVENTS` and `SEED_LLM_MODELS`. Read model statuses dynamically from `/api/system/models`.

### R2. Live Market Scanner Engine Hardening
Upgrade the backend scanner from paper stubs to real market scanning:
- In `skopaq/scanner/engine.py`: Replace `_default_quote_fetcher` (which returns `[]`) with real batch quote fetching across NIFTY 50 via `yfinance`/`INDstocks`. Compute real LTP, change%, volume ratio, and gap%.
- Replace `_default_llm_screener` with real inference using `instantiate_model("google", "gemini-flash-lite-latest")` evaluating metrics against `SCREEN_PROMPT_TEMPLATE`.
- In `skopaq/api/server.py`: Wire the `ScannerEngine` singleton in `_get_scanner()` with the real quote fetcher and real LLM screener so that `POST /api/scanner/scan` and `GET /api/scanner/candidates` return real live market opportunities.

### R3. Centralized Shared Paper Trading Engine
Unify the virtual paper trading state across all backend routers:
- In `skopaq/broker/paper_engine.py`: Implement `get_shared_paper_engine()` to ensure a single shared in-memory instance.
- Update `skopaq/api/server.py`, `skopaq/api/performance_router.py`, `skopaq/api/safety_router.py`, `skopaq/chat/session.py`, and `skopaq/chat/tools.py` to use `get_shared_paper_engine()`.
- Ensure positions, executed orders, available cash, and realized/unrealized P&L remain consistent and synchronized across all endpoints.

### R4. Performance Metrics & Learning Tracker Truthfulness
- In `skopaq/api/performance_router.py`: Remove hardcoded `sharpe_ratio = 1.5` and `max_dd = 1.2` fallbacks; calculate Sharpe and Drawdown strictly from actual returns (returning 0.0 if trades < 5). In `/models`, return 0.0 accuracy and 0 predictions when no prediction history exists.
- In `skopaq/learning/tracker.py`: Gracefully query Supabase via `get_safe_supabase()` or in-memory trade history when Postgres URL is absent, returning truthful zeroed metrics rather than raising connection exceptions.

### R5. Chat Assistant Bridge & Multi-Modal Text Extraction
- In `skopaq/chat/bridge.py`: Robustly extract text from `msg.content` (handling both strings and Google GenAI block lists `[{'type': 'text', ...}]`) using `_extract_text` so raw JSON repr is never sent to the user.
- In `frontend/src/lib/api.ts`: Increase request timeout for `/api/chat/message` to 45 seconds to accommodate tool execution and multi-agent lookups without premature client aborts.

## Acceptance Criteria

### Codebase & Static Verification
- [ ] No occurrences of `SEED_CANDIDATES`, `SEED_TRADES`, `SEED_SNAPSHOTS`, `SEED_MODEL_ACCURACIES`, `SEED_HEALING_EVENTS`, or `handleSimulatedResponse` exist in `frontend/src/`.
- [ ] Frontend builds cleanly with zero TypeScript errors (`node ./node_modules/typescript/lib/tsc.js --noEmit`).
- [ ] Backend compiles cleanly with zero syntax or flake8 errors (`python -m flake8 --select=E9,F skopaq`).

### Functional Verification
- [ ] `GET /api/portfolio` returns truthful cash (₹10,00,000.00) and empty positions list `[]` (0 fake positions).
- [ ] `POST /api/scanner/scan` executes a real live scan over NIFTY 50 with live prices and momentum metrics.
- [ ] `GET /api/trades` returns 0 trades and 0% win rate when no trades have been executed.
- [ ] `GET /api/performance/metrics` returns 0.0 Sharpe and 0.0 Drawdown when no trade history exists.
- [ ] `/api/chat/message` responds with real LLM inference and tool calls without falling back to client-side simulations.
- [ ] Every frontend route (`/`, `/portfolio`, `/scanner`, `/trades`, `/analytics`, `/settings`, `/chat`) renders with HTTP 200 and truthful empty states.
