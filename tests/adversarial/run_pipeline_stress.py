"""Standalone empirical stress runner for NovaPipeline orchestrator.

Executes 4 stress dimensions:
1. Concurrency Stress (multiple symbols simultaneously across run() and stream())
2. Partial Failure Fault Tolerance (3 of 7 analysts failing/None)
3. Stream Cancellation & Dangling Coroutine Leak Detection
4. High-Volume / Large Event Payload Throughput Stress
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import sys
import os
sys.path.insert(0, os.path.abspath("."))
import time
import warnings
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from novaswarm.api.analysis_models import DecisionCard
from novaswarm.orchestration.context import AnalysisContext
from novaswarm.orchestration.engine import NovaPipeline
from tests.adversarial.test_nova_pipeline_stress import AdversarialMockLLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline_stress_runner")


async def run_concurrency_stress(concurrency: int = 10) -> Dict[str, Any]:
    """Test concurrent runs of NovaPipeline.run() and stream() across multiple symbols."""
    logger.info("Running Concurrency Stress across %d symbols...", concurrency)
    symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
        "TATASTEEL", "MARUTI", "SUNPHARMA", "AXISBANK", "TITAN"
    ][:concurrency]

    llm = AdversarialMockLLM(min_delay=0.01, max_delay=0.02)
    pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

    start_t = time.monotonic()

    async def execute_symbol(sym: str, idx: int):
        if idx % 2 == 0:
            ctx = await pipeline.run(symbol=sym)
            return {"type": "run", "symbol": sym, "status": ctx.status, "duration": ctx.duration_seconds}
        else:
            evts = []
            async for evt in pipeline.stream(symbol=sym):
                evts.append(evt)
            return {"type": "stream", "symbol": sym, "status": evts[-1]["event"], "event_count": len(evts)}

    tasks = [execute_symbol(sym, i) for i, sym in enumerate(symbols)]
    results = await asyncio.gather(*tasks)
    elapsed = round(time.monotonic() - start_t, 3)

    successful = [r for r in results if r["status"] in ("completed", "job_completed")]
    success_rate = (len(successful) / len(results)) * 100.0

    return {
        "concurrency": concurrency,
        "elapsed_seconds": elapsed,
        "peak_active_llm_calls": llm.peak_active_calls,
        "total_llm_calls": llm.total_calls,
        "success_rate_pct": success_rate,
        "all_passed": success_rate == 100.0,
    }


async def run_partial_failure_stress() -> Dict[str, Any]:
    """Test 3 of 7 analysts failing (exceptions or returning None)."""
    logger.info("Running Partial Analyst Failure Stress (3 of 7 analysts failing)...")
    all_7_analysts = [
        "technical", "sentiment", "macro", "valuation",
        "network", "tokenomics", "derivatives"
    ]

    llm = AdversarialMockLLM()
    pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

    async def mock_analyst_worker(role: str, context: AnalysisContext) -> Any:
        if role == "sentiment":
            raise ConnectionResetError("Sentiment socket disconnected")
        elif role == "network":
            raise TimeoutError("Blockchain node RPC timeout")
        elif role == "tokenomics":
            return None
        return f"### {role.capitalize()} Analyst Report\n\nNominal quantitative assessment for {context.symbol}."

    with patch.object(pipeline, "_run_analyst_worker", side_effect=mock_analyst_worker):
        ctx = await pipeline.run(
            symbol="BTC/USDT",
            asset_class="crypto",
            selected_analysts=all_7_analysts,
        )

    all_reported = len(ctx.analyst_reports) == 7
    downstream_ok = ctx.thesis_context.consensus is not None and ctx.final_decision is not None

    return {
        "total_analysts": 7,
        "failed_analysts": 3,
        "successful_analysts": 4,
        "pipeline_completed": ctx.status == "completed",
        "reports_aggregated": len(ctx.analyst_reports),
        "downstream_succeeded": downstream_ok,
        "final_action": ctx.final_decision.action if ctx.final_decision else None,
        "final_confidence": ctx.final_decision.confidence if ctx.final_decision else None,
    }


async def run_cancellation_stress() -> Dict[str, Any]:
    """Test generator break during Stage 1 yield loop and check for unawaited coroutines."""
    logger.info("Running Stream Cancellation & Dangling Coroutine Test...")
    llm = AdversarialMockLLM()
    pipeline = NovaPipeline(llm_client=llm)

    leaked_warnings = []
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")

        gen = pipeline.stream(symbol="CANCEL_TEST")
        async for evt in gen:
            # Break immediately upon encountering the first agent_status
            if evt["event"] == "agent_status":
                break
        await gen.aclose()

        gc.collect()
        await asyncio.sleep(0.05)

        for w in recorded_warnings:
            if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower():
                leaked_warnings.append(str(w.message))

    return {
        "cancelled_at_event": "agent_status",
        "unawaited_coroutines_count": len(leaked_warnings),
        "warnings": leaked_warnings,
        "has_coroutine_leak": len(leaked_warnings) > 0,
    }


async def run_large_payload_stress() -> Dict[str, Any]:
    """Test 1.2MB event payload streaming and rapid consumption."""
    logger.info("Running Large Payload & Rapid Consumption Stress...")
    # 300,000 chars * 4 analysts = 1.2MB
    llm = AdversarialMockLLM(payload_size_chars=300000)
    pipeline = NovaPipeline(llm_client=llm, max_debate_rounds=1, max_risk_rounds=1)

    start_t = time.monotonic()
    events = []
    total_bytes = 0

    async for evt in pipeline.stream(symbol="BIG_PAYLOAD"):
        events.append(evt)
        serialized = json.dumps(evt, default=str)
        total_bytes += len(serialized.encode("utf-8"))

    elapsed = round(time.monotonic() - start_t, 3)

    return {
        "event_count": len(events),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "elapsed_seconds": elapsed,
        "throughput_mb_s": round((total_bytes / (1024 * 1024)) / max(0.001, elapsed), 2),
        "completed": events[-1]["event"] == "job_completed",
    }


async def main():
    print("=" * 70)
    print("NOVA PIPELINE ADVERSARIAL EMPIRICAL STRESS TEST SUITE")
    print("=" * 70)

    concurrency_res = await run_concurrency_stress(10)
    partial_failure_res = await run_partial_failure_stress()
    cancellation_res = await run_cancellation_stress()
    large_payload_res = await run_large_payload_stress()

    overall_results = {
        "concurrency_stress": concurrency_res,
        "partial_failure_stress": partial_failure_res,
        "cancellation_stress": cancellation_res,
        "large_payload_stress": large_payload_res,
        "verdict": "REQUEST_CHANGES" if cancellation_res["has_coroutine_leak"] else "APPROVE",
    }

    out_path = os.path.join(os.path.dirname(__file__), "pipeline_stress_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(overall_results, f, indent=2)

    print("\n--- RESULTS SUMMARY ---")
    print(f"Concurrency Stress (10 symbols): Success Rate {concurrency_res['success_rate_pct']}% in {concurrency_res['elapsed_seconds']}s")
    print(f"Partial Failure (3/7 analysts): Handled={partial_failure_res['pipeline_completed']}, Downstream={partial_failure_res['downstream_succeeded']}")
    print(f"Large Payload: {large_payload_res['total_mb']} MB streamed in {large_payload_res['elapsed_seconds']}s ({large_payload_res['throughput_mb_s']} MB/s)")
    print(f"Stream Cancellation: Coroutine Leak Count = {cancellation_res['unawaited_coroutines_count']}")
    if cancellation_res["has_coroutine_leak"]:
        print("  WARNING: Dangling unawaited coroutines detected!")
        for w in cancellation_res["warnings"]:
            print(f"    - {w}")

    print(f"\nFinal Challenger Verdict: {overall_results['verdict']}")
    print("=" * 70)

    return 1 if cancellation_res["has_coroutine_leak"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
