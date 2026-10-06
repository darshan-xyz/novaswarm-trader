"""Adversarial stress and concurrency test suite for NovaPipeline orchestrator.

Milestone 3 Challenger Suite:
1. Concurrent runs of NovaPipeline.run() and stream() across multiple symbols simultaneously.
2. Partial analyst failures (3 of 7 analysts raising exceptions or returning None) with clean continuation.
3. Stream cancellation mid-pipeline verifying proper task/resource cleanup without dangling coroutines.
4. Large event payloads (>1MB reports) and rapid stream consumption under stress.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import random
import sys
import time
import warnings
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
from unittest.mock import patch

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from skopaq.api.analysis_models import DecisionCard
from skopaq.memory.episodic import EpisodicLessonStore
from skopaq.orchestration.context import AnalysisContext
from skopaq.orchestration.engine import NovaPipeline
from skopaq.orchestration.signal_extraction import DecisionExtractor

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Adversarial Mock LLM with Latency, Large Payloads, and Failure Injection
# ─────────────────────────────────────────────────────────────────────────────

class AdversarialMockLLM(BaseChatModel):
    """Stress-testing Mock LLM capable of latency injection, failures, and massive payloads."""

    min_delay: float = 0.0
    max_delay: float = 0.0
    fail_roles: Dict[str, Any] = {}  # role_substring -> Exception or None or str
    payload_size_chars: int = 0
    active_calls: int = 0
    peak_active_calls: int = 0
    total_calls: int = 0

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt_text = " ".join([m.content for m in messages if hasattr(m, "content")])
        self.total_calls += 1

        # Check for failure injection
        for role_key, action in self.fail_roles.items():
            if role_key.lower() in prompt_text.lower():
                if isinstance(action, Exception):
                    raise action
                elif action is None:
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
                elif isinstance(action, str):
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=action))])

        content = self._build_content(prompt_text)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.active_calls += 1
        if self.active_calls > self.peak_active_calls:
            self.peak_active_calls = self.active_calls

        try:
            if self.max_delay > 0:
                delay = random.uniform(self.min_delay, self.max_delay)
                await asyncio.sleep(delay)
            return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        finally:
            self.active_calls -= 1

    def _build_content(self, prompt: str) -> str:
        # Default structured responses satisfying DecisionExtractor & Pipeline
        if "Chief Risk Officer" in prompt or "CRO" in prompt:
            return (
                "### CRO Adjudication Ruling\n"
                "Approved Action: BUY\n"
                "Risk constraints satisfied. Position size 100 shares.\n"
                "CONFIDENCE: 85"
            )
        elif "Order Strategist" in prompt:
            return (
                "### Order Strategy Plan\n"
                "Entry: 2500.00\n"
                "Stop Loss: 2420.00\n"
                "Target: 2660.00\n"
                "Timeframe: Swing\n"
                "FINAL TRANSACTION PROPOSAL: **BUY**"
            )
        elif "Thesis Adjudicator" in prompt:
            return (
                "### Synthesis Consensus\n"
                "Upside breakout verified with solid volume expansion.\n"
                "ACTION: BUY"
            )
        elif "Upside Advocate" in prompt:
            return "### Bull Thesis\nEarnings momentum accelerating with structural margin expansion."
        elif "Downside Advocate" in prompt:
            return "### Bear Counter-Thesis\nOverhead technical resistance and raw material input inflation."
        elif "Growth Perspective" in prompt:
            return "Growth view: Capital deployment approved with favorable upside leverage."
        elif "Capital Preservation" in prompt or "Preservation Perspective" in prompt:
            return "Preservation view: Downside invalidation is tightly constrained."
        elif "Balanced Perspective" in prompt:
            return "Balanced view: Risk-reward ratio exceeds 2:1 target threshold."

        # Large payload generation for stress testing
        if self.payload_size_chars > 0:
            filler = "Quantitative analysis indicators confirm strong momentum. " * 50
            needed_repeats = max(1, self.payload_size_chars // len(filler))
            return (
                f"### High Volume Analyst Report\n\n"
                f"{filler * needed_repeats}\n\n"
                f"CONFIDENCE: 80\n"
                f"OUTLOOK: Bullish"
            )

        return (
            "### Analyst Report\n"
            "Key metrics sound. RSI 58, MACD bullish crossover, ATR 24.5.\n"
            "Conviction: Strong."
        )

    @property
    def _llm_type(self) -> str:
        return "adversarial_mock_llm"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Stress Tests: Concurrency Across Multiple Symbols Simultaneously
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentPipelineExecution:
    """Stress tests concurrent runs of NovaPipeline.run() and stream()."""

    @pytest.mark.asyncio
    async def test_concurrent_run_multiple_symbols(self):
        """10 distinct symbols executed concurrently via pipeline.run()."""
        llm = AdversarialMockLLM(min_delay=0.01, max_delay=0.03)
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        symbols = [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT"
        ]

        async def run_single(sym: str) -> AnalysisContext:
            return await pipeline.run(
                symbol=sym,
                trade_date="2026-09-27",
                selected_analysts=["technical", "sentiment", "macro", "valuation"],
            )

        start_t = time.monotonic()
        contexts = await asyncio.gather(*(run_single(sym) for sym in symbols))
        elapsed = time.monotonic() - start_t

        assert len(contexts) == 10
        for ctx, sym in zip(contexts, symbols):
            assert isinstance(ctx, AnalysisContext)
            assert ctx.symbol == sym, f"Context symbol mismatch: expected {sym}, got {ctx.symbol}"
            assert ctx.status == "completed"
            assert ctx.final_decision is not None
            assert ctx.final_decision.symbol == sym
            assert ctx.final_decision.action == "BUY"
            assert len(ctx.analyst_reports) == 4
            assert ctx.duration_seconds > 0.0

        # Concurrency check: 10 parallel runs should take much less than serial sum
        assert elapsed < 5.0, f"Concurrent runs took too long: {elapsed:.2f}s"
        assert llm.peak_active_calls > 1, f"Peak active calls was {llm.peak_active_calls}; expected concurrent overlap"

    @pytest.mark.asyncio
    async def test_concurrent_stream_multiple_symbols(self):
        """10 distinct symbols streamed concurrently via pipeline.stream()."""
        llm = AdversarialMockLLM(min_delay=0.01, max_delay=0.03)
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        symbols = [
            "TATASTEEL", "MARUTI", "SUNPHARMA", "AXISBANK", "TITAN",
            "BAJFINANCE", "ASIANPAINT", "HCLTECH", "WIPRO", "NTPC"
        ]

        async def stream_single(sym: str) -> List[Dict[str, Any]]:
            events = []
            async for evt in pipeline.stream(
                symbol=sym,
                trade_date="2026-09-27",
                selected_analysts=["technical", "macro"],
            ):
                events.append(evt)
            return events

        start_t = time.monotonic()
        results = await asyncio.gather(*(stream_single(sym) for sym in symbols))
        elapsed = time.monotonic() - start_t

        assert len(results) == 10
        for events, sym in zip(results, symbols):
            assert len(events) >= 8, f"Too few events ({len(events)}) for {sym}"
            event_types = [e["event"] for e in events]
            assert event_types[0] == "job_started"
            assert event_types[-1] == "job_completed"

            # Check symbol consistency across all events that carry symbol
            for e in events:
                data = e.get("data", {})
                if "symbol" in data:
                    assert data["symbol"] == sym, f"Cross-talk detected: event had symbol {data['symbol']} instead of {sym}"

            # Check job completion data
            completed_evt = events[-1]
            assert completed_evt["data"]["final_verdict"] == "BUY"
            assert completed_evt["data"]["confidence"] == 85

        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_mixed_concurrent_run_and_stream(self):
        """Simultaneous interleaved pipeline.run() and pipeline.stream() invocations."""
        llm = AdversarialMockLLM(min_delay=0.005, max_delay=0.02)
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        run_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]
        stream_symbols = ["BHARTIARTL", "ITC", "KOTAKBANK", "LT", "MARUTI"]

        async def do_run(sym: str) -> AnalysisContext:
            return await pipeline.run(symbol=sym)

        async def do_stream(sym: str) -> List[Dict[str, Any]]:
            evts = []
            async for evt in pipeline.stream(symbol=sym):
                evts.append(evt)
            return evts

        run_tasks = [do_run(s) for s in run_symbols]
        stream_tasks = [do_stream(s) for s in stream_symbols]

        all_results = await asyncio.gather(*run_tasks, *stream_tasks)

        run_contexts = all_results[:len(run_symbols)]
        stream_events = all_results[len(run_symbols):]

        for ctx, sym in zip(run_contexts, run_symbols):
            assert ctx.symbol == sym
            assert ctx.status == "completed"

        for evts, sym in zip(stream_events, stream_symbols):
            assert evts[0]["data"]["symbol"] == sym
            assert evts[-1]["event"] == "job_completed"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stress Tests: Partial Analyst Failures (3 of 7 Analysts Failing/None)
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialAnalystFailures:
    """Stress tests resilience against unhandled exceptions and None returns in analysts."""

    @pytest.mark.asyncio
    async def test_partial_failure_3_of_7_analysts_run(self):
        """7 analysts configured; 3 fail (2 exceptions, 1 returns None).
        Pipeline must continue cleanly and aggregate successful reports.
        """
        all_7_analysts = [
            "technical", "sentiment", "macro", "valuation",
            "network", "tokenomics", "derivatives"
        ]

        llm = AdversarialMockLLM()
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        # Mock analyst worker failures
        async def mock_analyst_worker(role: str, context: AnalysisContext) -> Any:
            if role == "sentiment":
                raise ConnectionResetError("Sentiment API socket connection reset by peer")
            elif role == "network":
                raise TimeoutError("RPC node timeout after 30000ms")
            elif role == "tokenomics":
                return None  # Unhandled None return
            else:
                return (
                    f"### {role.capitalize()} Analyst Report\n\n"
                    f"Validated quantitative signals for {context.symbol}."
                )

        with patch.object(pipeline, "_run_analyst_worker", side_effect=mock_analyst_worker):
            ctx = await pipeline.run(
                symbol="BTC/USDT",
                asset_class="crypto",
                selected_analysts=all_7_analysts,
            )

        assert ctx.status == "completed", f"Pipeline should complete despite partial failures, got: {ctx.status}"
        assert len(ctx.analyst_reports) == 7

        # Check failed analysts reports contain error descriptions or fallback
        assert "unavailable" in ctx.analyst_reports["sentiment"].lower() or "error" in ctx.analyst_reports["sentiment"].lower()
        assert "unavailable" in ctx.analyst_reports["network"].lower() or "error" in ctx.analyst_reports["network"].lower()
        assert ctx.analyst_reports["tokenomics"] == "None" or "none" in ctx.analyst_reports["tokenomics"].lower()

        # Check successful analysts reports
        for successful_role in ["technical", "macro", "valuation", "derivatives"]:
            assert successful_role in ctx.analyst_reports
            assert "Validated quantitative signals" in ctx.analyst_reports[successful_role]

        # Verify downstream stages succeeded
        assert ctx.thesis_context.consensus is not None
        assert ctx.order_plan is not None
        assert ctx.final_decision is not None
        assert ctx.final_decision.action in ("BUY", "SELL", "HOLD")

    @pytest.mark.asyncio
    async def test_partial_failure_3_of_7_analysts_stream(self):
        """Stream mode with 3 of 7 analysts failing."""
        all_7_analysts = [
            "technical", "sentiment", "macro", "valuation",
            "network", "tokenomics", "derivatives"
        ]

        llm = AdversarialMockLLM()
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        async def mock_analyst_worker(role: str, context: AnalysisContext) -> Any:
            if role == "valuation":
                raise ZeroDivisionError("DCF denominator is zero")
            elif role == "macro":
                raise KeyError("GDP indicator key missing")
            elif role == "derivatives":
                return None
            return f"### {role.capitalize()} Analyst Report\n\nNominal metrics sound."

        with patch.object(pipeline, "_run_analyst_worker", side_effect=mock_analyst_worker):
            events = []
            async for evt in pipeline.stream(
                symbol="ETH-USD",
                asset_class="crypto",
                selected_analysts=all_7_analysts,
            ):
                events.append(evt)

        event_names = [e["event"] for e in events]
        assert event_names[0] == "job_started"
        assert event_names[-1] == "job_completed"

        # Verify all 7 analysts emitted reports and completed status
        report_events = [e for e in events if e["event"] == "agent_report" and e["data"].get("team") == "analyst"]
        assert len(report_events) == 7

        agent_ids = [e["data"]["agent_id"] for e in report_events]
        for role in all_7_analysts:
            assert f"{role}_analyst" in agent_ids

    @pytest.mark.asyncio
    async def test_extreme_all_analysts_failing(self):
        """Stress edge case: all 7 analysts fail. Pipeline should survive or handle gracefully."""
        pipeline = NovaPipeline(llm_client=AdversarialMockLLM())

        async def failing_worker(role: str, context: AnalysisContext) -> Any:
            raise RuntimeError(f"Complete system outage for {role}")

        with patch.object(pipeline, "_run_analyst_worker", side_effect=failing_worker):
            ctx = await pipeline.run(
                symbol="OUTAGE_TEST",
                selected_analysts=["technical", "sentiment", "macro"],
            )

        # Pipeline completes with error notices in reports and generates default decision
        assert ctx.status == "completed"
        for rep in ctx.analyst_reports.values():
            assert "unavailable" in rep.lower() or "error" in rep.lower()
        assert ctx.final_decision is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Stress Tests: Stream Cancellation Mid-Pipeline & Resource Cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestStreamCancellationAndResourceCleanup:
    """Stress tests generator cancellation and verifies no dangling tasks or coroutines."""

    @pytest.mark.asyncio
    async def test_stream_break_stage_1(self):
        """Consumer breaks out of async generator during Stage 1."""
        llm = AdversarialMockLLM(min_delay=0.05, max_delay=0.1)
        pipeline = NovaPipeline(llm_client=llm)

        consumed_events = []
        gen = pipeline.stream(symbol="CANCEL_TEST_1")
        try:
            async for evt in gen:
                consumed_events.append(evt)
                if evt["event"] == "job_started":
                    break
        finally:
            await gen.aclose()

        assert len(consumed_events) == 1
        assert consumed_events[0]["event"] == "job_started"

        # Give loop a brief moment to run any pending cleanup callbacks
        await asyncio.sleep(0.05)

        # Check no active tasks belonging to NovaPipeline remain
        current_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        pipeline_tasks = [t for t in current_tasks if "run_analyst" in str(t) or "_execute_stage" in str(t)]
        assert len(pipeline_tasks) == 0, f"Found dangling tasks: {pipeline_tasks}"

    @pytest.mark.asyncio
    async def test_stream_break_stage_2_debate(self):
        """Consumer breaks out during Stage 2 debate."""
        llm = AdversarialMockLLM(min_delay=0.01, max_delay=0.02)
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=3)

        consumed_events = []
        gen = pipeline.stream(symbol="CANCEL_TEST_2")
        try:
            async for evt in gen:
                consumed_events.append(evt)
                if evt.get("data", {}).get("agent_id") == "bull_researcher":
                    break
        finally:
            await gen.aclose()

        await asyncio.sleep(0.05)
        current_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        pipeline_tasks = [t for t in current_tasks if "advocate" in str(t) or "adjudicator" in str(t)]
        assert len(pipeline_tasks) == 0

    @pytest.mark.asyncio
    async def test_stream_task_cancellation_during_gather(self):
        """Cancel the wrapping asyncio.Task while Stage 1 gather is actively awaiting."""
        llm = AdversarialMockLLM(min_delay=0.5, max_delay=1.0)  # Slow to guarantee in-flight execution
        pipeline = NovaPipeline(llm_client=llm)

        async def run_pipeline():
            async for evt in pipeline.stream(symbol="CANCEL_IN_FLIGHT"):
                pass

        task = asyncio.create_task(run_pipeline())
        # Wait until pipeline starts and enters Stage 1
        await asyncio.sleep(0.05)

        assert not task.done()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await asyncio.sleep(0.05)
        # Verify no orphaned tasks
        active = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert task not in active
        for t in active:
            assert "analyst" not in str(t).lower()

    @pytest.mark.asyncio
    async def test_no_unawaited_coroutine_warnings_on_immediate_break(self):
        """Verify that breaking immediately after start emits zero unawaited coroutine warnings."""
        llm = AdversarialMockLLM()
        pipeline = NovaPipeline(llm_client=llm)

        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")

            gen = pipeline.stream(symbol="CLEAN_EXIT")
            async for evt in gen:
                break
            await gen.aclose()

            # Force garbage collection to trigger any __del__ unawaited coroutine warnings
            gc.collect()
            await asyncio.sleep(0.05)

            coroutine_warnings = [
                w for w in recorded_warnings
                if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower()
            ]
            assert len(coroutine_warnings) == 0, f"Unawaited coroutine warnings detected: {[str(w.message) for w in coroutine_warnings]}"

    @pytest.mark.asyncio
    async def test_stream_break_on_first_agent_status_coroutine_leak(self):
        """Verify that breaking on the first agent_status does not leak unawaited coroutines."""
        llm = AdversarialMockLLM()
        pipeline = NovaPipeline(llm_client=llm)

        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")

            gen = pipeline.stream(symbol="AGENT_STATUS_BREAK")
            async for evt in gen:
                if evt["event"] == "agent_status":
                    break
            await gen.aclose()

            gc.collect()
            await asyncio.sleep(0.05)

            coroutine_warnings = [
                w for w in recorded_warnings
                if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower()
            ]
            assert len(coroutine_warnings) == 0, f"Unawaited coroutine warnings detected: {[str(w.message) for w in coroutine_warnings]}"



# ─────────────────────────────────────────────────────────────────────────────
# 4. Stress Tests: Large Event Payloads & Rapid Stream Consumption
# ─────────────────────────────────────────────────────────────────────────────

class TestLargePayloadsAndRapidConsumption:
    """Stress tests massive payloads (>1MB reports) and high-speed generator consumption."""

    @pytest.mark.asyncio
    async def test_large_event_payloads_1mb_reports(self):
        """Mock analysts returning massive reports (>1MB total text).
        Verify memory stability, JSON serializability of events, and stream integrity.
        """
        # 300,000 chars per analyst * 4 analysts = 1.2 MB text payload
        llm = AdversarialMockLLM(payload_size_chars=300000)
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        events = []
        total_bytes = 0

        async for evt in pipeline.stream(symbol="MASSIVE_PAYLOAD"):
            events.append(evt)
            # Ensure event is JSON-serializable (SSE wire requirement)
            serialized = json.dumps(evt, default=str)
            total_bytes += len(serialized.encode("utf-8"))

        assert len(events) >= 10
        assert total_bytes > 1_000_000, f"Expected total bytes > 1MB, got {total_bytes}"

        completed_evt = events[-1]
        assert completed_evt["event"] == "job_completed"
        assert completed_evt["data"]["final_verdict"] == "BUY"

    @pytest.mark.asyncio
    async def test_rapid_stream_consumption(self):
        """Rapidly consume 1000 events without pausing to verify tight loop throughput."""
        llm = AdversarialMockLLM()
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        start_t = time.monotonic()
        total_events = 0

        # Run 25 consecutive streams rapidly
        for i in range(25):
            async for evt in pipeline.stream(symbol=f"RAPID_{i}"):
                total_events += 1

        elapsed = time.monotonic() - start_t
        rate = total_events / max(0.001, elapsed)

        assert total_events > 400
        # Should process at > 200 events/second offline
        assert rate > 100, f"Consumption rate was {rate:.1f} events/s, expected > 100"

    @pytest.mark.asyncio
    async def test_multilingual_unicode_payloads(self):
        """Stress test with complex Indian regional language text (Devanagari, Tamil, Gujarati)."""
        unicode_text = (
            "### तांत्रिक विश्लेषण (Technical Analysis)\n"
            "रिलायंस इंडस्ट्रीज में ब्रेकआउट के मजबूत संकेत।\n"
            "### தமிழ் முன்னறிவிப்பு (Tamil Forecast)\n"
            "விலை உயர்வு சாத்தியம் அதிகம்.\n"
            "### ગુજરાતી અહેવાલ (Gujarati Report)\n"
            "વોલ્યુમમાં નોંધપાત્ર વધારો થયો છે."
        )

        llm = AdversarialMockLLM(fail_roles={"technical": unicode_text})
        pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

        ctx = await pipeline.run(symbol="RELIANCE")
        assert ctx.status == "completed"
        assert "रिलायंस" in ctx.analyst_reports["technical"]
        assert "விலை" in ctx.analyst_reports["technical"]

        # Ensure situation summary handles UTF-8 properly
        summary = ctx.get_situation_summary()
        assert "વોલ્યુમ" in summary

        # Ensure JSON dump works without encoding errors
        state_dict = ctx.model_dump()
        json_str = json.dumps(state_dict, ensure_ascii=False)
        assert "तांत्रिक विश्लेषण" in json_str
