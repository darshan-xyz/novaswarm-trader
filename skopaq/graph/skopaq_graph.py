"""Skopaq Native Trading Graph: NovaPipeline multi-agent orchestrator + execution pipeline.

This is the main entry point for running an analysis-and-trade cycle.
It coordinates the 5-stage native async consensus pipeline, then routes the
decision through safety checks and order execution.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from skopaq.broker.models import Exchange, ExecutionResult, TradingSignal
from skopaq.execution.executor import Executor

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Complete result of an analyze-and-execute cycle."""

    symbol: str
    trade_date: str
    signal: Optional[TradingSignal] = None
    execution: Optional[ExecutionResult] = None
    agent_state: dict[str, Any] = field(default_factory=dict)
    raw_decision: str = ""
    error: Optional[str] = None
    duration_seconds: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    trade_id: Optional[UUID] = None  # Set after DB persistence in _run_lifecycle
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NovaPipelineAdapter:
    """Drop-in adapter wrapping NovaPipeline for execution interfaces."""

    def __init__(
        self,
        selected_analysts: Optional[list[str]] = None,
        debug: bool = False,
        config: Optional[dict[str, Any]] = None,
    ):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config or {}

        from skopaq.memory.episodic import EpisodicLessonStore
        from skopaq.llm.client_factory import instantiate_model
        from skopaq.orchestration.engine import NovaPipeline
        from skopaq.orchestration.reflection import PostTradeReflector

        self.bull_memory = EpisodicLessonStore("bull_memory")
        self.bear_memory = EpisodicLessonStore("bear_memory")
        self.trader_memory = EpisodicLessonStore("trader_memory")
        self.invest_judge_memory = EpisodicLessonStore("invest_judge_memory")
        self.risk_manager_memory = EpisodicLessonStore("risk_manager_memory")

        provider = self.config.get("llm_provider", "google")
        model = self.config.get("deep_think_llm", "gemini-flash-latest")
        base_url = self.config.get("backend_url")
        self.llm = instantiate_model(provider=provider, model=model, base_url=base_url)

        self.pipeline = NovaPipeline(
            llm_client=self.llm,
            memory_store=self.risk_manager_memory,
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_rounds=self.config.get("max_risk_discuss_rounds", 1),
            config=self.config,
        )
        self.curr_state: dict[str, Any] = {}
        self.reflector = PostTradeReflector(self.llm)

    async def analyze_async(self, symbol: str, trade_date: str) -> tuple[dict[str, Any], str]:
        """Execute native async pipeline directly without thread-switching."""
        ctx = await self.pipeline.run(
            symbol=symbol,
            trade_date=str(trade_date),
            selected_analysts=self.selected_analysts,
            asset_class=self.config.get("asset_class", "equity"),
        )
        state = ctx.to_legacy_state()
        self.curr_state = state
        action = ctx.final_decision.action if ctx.final_decision else "HOLD"
        return state, action

    def propagate(self, company_name: str, trade_date: str) -> tuple[dict[str, Any], str]:
        """Synchronous wrapper for legacy callers."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run, self.analyze_async(company_name, trade_date)
                ).result()
        else:
            return asyncio.run(self.analyze_async(company_name, trade_date))

    def reflect_and_remember(self, returns_losses: Any) -> None:
        """Update episodic memories after position close."""
        situation = f"{self.curr_state.get('market_report', '')}\n\n{self.curr_state.get('fundamentals_report', '')}"
        advice = f"Realized outcome: {returns_losses}. Reinforce trend alignment and adherence to stop losses."
        for mem in (self.bull_memory, self.bear_memory, self.trader_memory, self.invest_judge_memory, self.risk_manager_memory):
            mem.add_situations([(situation, advice)])


class SkopaqTradingGraph:
    """Wraps native NovaPipeline multi-agent orchestrator with Skopaq execution.

    Pipeline::

        analyze(symbol, date)  →  parse signal  →  executor.execute_signal()

    When a ``MemoryStore`` is provided, memories are loaded from Supabase
    before the first pipeline run, and saved back after reflection.

    Args:
        upstream_config: Config dict for NovaPipeline (LLM keys, etc).
        executor: The Skopaq execution pipeline (safety → route → fill).
        selected_analysts: Which analysts to enable.
        debug: Enable debug/tracing mode.
        memory_store: Optional persistence layer for agent memories.
    """

    def __init__(
        self,
        upstream_config: dict[str, Any],
        executor: Executor,
        selected_analysts: Optional[list[str]] = None,
        debug: bool = False,
        memory_store: Optional[Any] = None,
    ) -> None:
        self._executor = executor
        self._upstream_config = upstream_config

        # Default analyst selection: base 4 + crypto-specific when asset_class == "crypto"
        if selected_analysts is not None:
            self._selected_analysts = selected_analysts
        else:
            base = ["market", "social", "news", "fundamentals"]
            if upstream_config.get("asset_class") == "crypto":
                self._selected_analysts = base + ["onchain", "defi", "funding"]
            else:
                self._selected_analysts = base
        self._debug = debug
        self._memory_store = memory_store
        self._graph: Any = None  # Lazy-init pipeline adapter

    def _ensure_graph(self) -> Any:
        """Lazy-import and initialise the native NovaPipelineAdapter."""
        if self._graph is not None:
            return self._graph

        # Bridge SKOPAQ_ env vars → standard LLM env vars before init
        from skopaq.llm.env_bridge import bridge_env_vars
        bridge_env_vars()

        self._graph = NovaPipelineAdapter(
            selected_analysts=self._selected_analysts,
            debug=self._debug,
            config=self._upstream_config,
        )
        logger.info(
            "Native NovaPipelineAdapter initialised (analysts=%s, debug=%s)",
            self._selected_analysts, self._debug,
        )

        # Restore persisted memories into memory objects
        if self._memory_store is not None:
            try:
                loaded = self._memory_store.load(self._graph)
                logger.info("Agent memories loaded from Supabase (%d entries)", loaded)
            except Exception:
                logger.warning("Memory load failed — agents will start with empty memory", exc_info=True)

        return self._graph

    async def analyze(self, symbol: str, trade_date: str) -> AnalysisResult:
        """Run native analysis without executing a trade.

        Useful for getting the agent's recommendation without placing an order.
        """
        import time

        start = time.monotonic()
        try:
            graph = self._ensure_graph()
            if hasattr(graph, "analyze_async"):
                state, decision = await graph.analyze_async(symbol, trade_date)
            else:
                state, decision = graph.propagate(symbol, trade_date)

            signal = self._parse_signal(symbol, decision, state)
            duration = time.monotonic() - start

            # Read semantic cache stats (if cache is active)
            cache_hits, cache_misses = self._read_cache_stats()

            return AnalysisResult(
                symbol=symbol,
                trade_date=trade_date,
                signal=signal,
                agent_state=state if isinstance(state, dict) else {},
                raw_decision=str(decision),
                duration_seconds=round(duration, 2),
                cache_hits=cache_hits,
                cache_misses=cache_misses,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            logger.exception("Analysis failed for %s", symbol)
            return AnalysisResult(
                symbol=symbol,
                trade_date=trade_date,
                error=str(exc),
                duration_seconds=round(duration, 2),
            )

    async def analyze_and_execute(
        self,
        symbol: str,
        trade_date: str,
        regime_scale: float = 1.0,
        calendar_scale: float = 1.0,
    ) -> AnalysisResult:
        """Run upstream analysis and execute the resulting signal.

        Full pipeline:
            1. ``upstream.propagate(symbol, date)``  — get agent decision
            2. Parse decision into a ``TradingSignal``
            3. ``executor.execute_signal(signal)``  — safety check → route → fill

        Args:
            symbol: Stock symbol to analyze and trade.
            trade_date: Trading date (YYYY-MM-DD).
            regime_scale: Market regime position multiplier (0.0–1.2).
            calendar_scale: Event calendar position multiplier (0.0–1.0).
        """
        result = await self.analyze(symbol, trade_date)

        if result.error:
            return result

        if result.signal is None or result.signal.action == "HOLD":
            logger.info("Signal is HOLD for %s — no execution", symbol)
            return result

        # Execute the signal through the full pipeline
        execution = await self._executor.execute_signal(
            result.signal,
            trade_date=trade_date,
            regime_scale=regime_scale,
            calendar_scale=calendar_scale,
        )
        result.execution = execution

        logger.info(
            "Cycle complete: %s %s → %s (success=%s, mode=%s)",
            result.signal.action, symbol, execution.mode,
            execution.success, execution.mode,
        )
        return result

    def reflect(self, returns_losses: Any) -> None:
        """Invoke episodic reflection to update agent memories.

        Called after a position close (SELL) to let agents learn from the
        realized P&L. After the reflection writes lessons into
        the in-memory BM25 stores, we persist them to Supabase so they
        survive across sessions.
        """
        graph = self._ensure_graph()
        graph.reflect_and_remember(returns_losses)
        logger.info("Episodic reflection complete")

        # Persist updated memories to Supabase
        if self._memory_store is not None:
            try:
                saved = self._memory_store.save(self._graph)
                logger.info("Agent memories saved to Supabase (%d entries)", saved)
            except Exception:
                logger.warning("Memory save failed — lessons will be lost on exit", exc_info=True)

    # ── Cache stats ────────────────────────────────────────────────────

    @staticmethod
    def _read_cache_stats() -> tuple[int, int]:
        """Read hit/miss counters from the global LLM cache (if active).

        Returns (hits, misses) — both 0 when no cache is configured.
        """
        try:
            from langchain_core.globals import get_llm_cache
            cache = get_llm_cache()
            if cache is not None and hasattr(cache, "stats"):
                stats = cache.stats
                logger.info(
                    "Cache: %d hits, %d misses (%.1f%% hit rate, %d errors)",
                    stats.hits, stats.misses, stats.hit_rate_pct, stats.errors,
                )
                return stats.hits, stats.misses
        except Exception:
            logger.debug("Could not read cache stats", exc_info=True)
        return 0, 0

    # ── Signal parsing ───────────────────────────────────────────────────

    def _parse_signal(
        self,
        symbol: str,
        decision: Any,
        state: Any,
    ) -> Optional[TradingSignal]:
        """Convert upstream decision into a typed TradingSignal.

        The upstream ``propagate()`` returns a (state, decision) tuple where
        ``decision`` is a processed signal string like "BUY" / "SELL" / "HOLD",
        and ``state`` is a dict with all intermediate analysis.

        Reasoning is extracted from (in priority order):
        1. ``risk_debate_state.judge_decision`` — the risk manager's verdict
        2. ``final_trade_decision`` — the full unprocessed report
        3. The raw decision string (fallback, usually just one word)
        """
        if decision is None:
            return None

        decision_str = str(decision).strip().upper()

        # Extract action
        if "BUY" in decision_str:
            action = "BUY"
        elif "SELL" in decision_str:
            action = "SELL"
        else:
            action = "HOLD"

        # Try to extract confidence from state
        confidence = 50
        reasoning = decision_str[:500]

        if isinstance(state, dict):
            # The risk management node may include a confidence indicator
            risk_state = state.get("risk_debate_state", {})
            if isinstance(risk_state, dict):
                confidence = _extract_confidence(risk_state)
                logger.debug("Signal confidence for %s: %d", symbol, confidence)
                # Judge decision has the richest reasoning
                judge = risk_state.get("judge_decision", "")
                if judge and len(str(judge).strip()) > len(action):
                    reasoning = str(judge).strip()[:2000]

            # Fall back to the full unprocessed trade decision
            if reasoning == decision_str[:500]:
                full_decision = state.get("final_trade_decision", "")
                if full_decision and len(str(full_decision).strip()) > len(action):
                    reasoning = str(full_decision).strip()[:2000]

        # Try to extract execution parameters from final_decision or order_plan
        entry_price = None
        stop_loss = None
        target = None
        quantity = None

        if isinstance(state, dict):
            dec = state.get("final_decision") or {}
            plan = state.get("order_plan") or {}
            if isinstance(dec, dict) and dec:
                entry_price = dec.get("entry_price")
                stop_loss = dec.get("stop_loss")
                target = dec.get("target")
                raw_qty = dec.get("quantity") or dec.get("position_size")
                if raw_qty is not None:
                    try:
                        quantity = Decimal(str(raw_qty))
                    except Exception:
                        quantity = None
            elif isinstance(plan, dict) and plan:
                entry_price = plan.get("entry_price")
                stop_loss = plan.get("stop_loss")
                target = plan.get("target")

        # Pick exchange based on asset class in upstream config
        asset_class = self._upstream_config.get("asset_class", "equity")
        exchange = Exchange.BINANCE if asset_class == "crypto" else Exchange.NSE

        return TradingSignal(
            symbol=symbol,
            exchange=exchange,
            action=action,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            quantity=quantity,
            reasoning=reasoning,
            agent_state=state if isinstance(state, dict) else {},
        )


def _extract_confidence(risk_state: dict[str, Any]) -> int:
    """Extract a confidence score from the risk debate state.

    Extraction priority:
    1. Parse ``CONFIDENCE: <N>`` from the judge_decision text.
    2. Check for explicit dict keys (forward-compatible).
    3. Heuristic: analyse debater agreement direction.
    4. Fallback: 50 (graceful degradation).
    """
    # --- Priority 1: Parse from judge_decision text ---
    judge_text = risk_state.get("judge_decision", "")
    if judge_text:
        # Normalise: extract_text handles Gemini list-of-dicts format
        from skopaq.llm import extract_text
        judge_text = extract_text(judge_text)

        match = re.search(r"(?i)confidence\s*:\s*(\d{1,3})", judge_text)
        if match:
            val = int(match.group(1))
            clamped = max(0, min(100, val))
            logger.debug("Parsed confidence from judge text: %d (clamped: %d)", val, clamped)
            return clamped

    # --- Priority 2: Check for explicit dict keys (forward-compatible) ---
    for key in ("confidence", "score", "certainty"):
        if key in risk_state:
            try:
                val = int(float(risk_state[key]))
                return max(0, min(100, val))
            except (ValueError, TypeError):
                pass

    # --- Priority 3: Heuristic from debater agreement ---
    count = risk_state.get("count", 0)
    if count > 0:
        aggressive = risk_state.get("current_aggressive_response", "")
        conservative = risk_state.get("current_conservative_response", "")
        neutral = risk_state.get("current_neutral_response", "")
        agreement = _estimate_agreement(aggressive, conservative, neutral)
        heuristic = int(35 + agreement * 50)
        logger.debug(
            "Heuristic confidence: %d (agreement=%.2f, rounds=%d)",
            heuristic, agreement, count,
        )
        return heuristic

    # --- Priority 4: Default fallback ---
    logger.debug("No confidence signal found — using default 50")
    return 50


def _estimate_agreement(aggressive: str, conservative: str, neutral: str) -> float:
    """Estimate how much the three risk debaters agree on direction.

    Returns 0.0–1.0 mapped to confidence 35–85 by the caller.
    """
    if not (aggressive and conservative and neutral):
        return 0.5  # Insufficient data → mid-range

    responses = [aggressive.upper(), conservative.upper(), neutral.upper()]
    buy_count = sum(1 for r in responses if "BUY" in r and "SELL" not in r)
    sell_count = sum(1 for r in responses if "SELL" in r and "BUY" not in r)
    hold_count = sum(1 for r in responses if "HOLD" in r)

    max_agreement = max(buy_count, sell_count, hold_count)

    if max_agreement == 3:
        return 1.0   # Unanimous
    elif max_agreement == 2:
        return 0.6   # Majority
    else:
        return 0.3   # Full disagreement
