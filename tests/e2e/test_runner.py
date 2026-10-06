#!/usr/bin/env python3
"""SkopaqTrader Standalone E2E Test Runner.

Executes all 4 tiers of opaque-box E2E test suites with dual-mode support:
- --mode mock (default): In-process high-fidelity mock ASGI application
- --mode live: Network HTTP/SSE requests against running backend and frontend

Usage:
    python tests/e2e/test_runner.py --mode mock
    python tests/e2e/test_runner.py --mode mock --tier 1
    python tests/e2e/test_runner.py --mode mock --feature trades
    python tests/e2e/test_runner.py --mode live --backend-url http://localhost:8000
    python tests/e2e/test_runner.py --mode mock --json-report test_report.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.client import E2EClient


# ── TEST SUITE REGISTRY ──────────────────────────────────────────────────────

TIER_MODULES: Dict[str, List[str]] = {
    "1": [
        "tests.e2e.tier1_features.test_trades",
        "tests.e2e.tier1_features.test_analysis_sse",
        "tests.e2e.tier1_features.test_memory",
        "tests.e2e.tier1_features.test_performance",
        "tests.e2e.tier1_features.test_safety",
        "tests.e2e.tier1_features.test_system",
        "tests.e2e.tier1_features.test_chat",
        "tests.e2e.tier1_features.test_frontend_routes",
    ],
    "2": [
        "tests.e2e.tier2_boundaries.test_trades_boundaries",
        "tests.e2e.tier2_boundaries.test_analysis_boundaries",
        "tests.e2e.tier2_boundaries.test_memory_boundaries",
        "tests.e2e.tier2_boundaries.test_performance_boundaries",
        "tests.e2e.tier2_boundaries.test_safety_boundaries",
        "tests.e2e.tier2_boundaries.test_system_boundaries",
        "tests.e2e.tier2_boundaries.test_chat_boundaries",
        "tests.e2e.tier2_boundaries.test_frontend_boundaries",
    ],
    "3": [
        "tests.e2e.tier3_combinations.test_cross_feature_combinations",
    ],
    "4": [
        "tests.e2e.tier4_scenarios.test_real_world_scenarios",
    ],
}


class TestCaseInfo:
    __test__ = False

    def __init__(self, tier: str, module_name: str, test_name: str, test_func: Callable):
        self.tier = tier
        self.module_name = module_name
        self.test_name = test_name
        self.test_func = test_func
        # Determine feature category from module name
        self.feature = module_name.split(".")[-1].replace("test_", "").replace("_boundaries", "")


class TestResult:
    __test__ = False

    def __init__(
        self,
        test_info: TestCaseInfo,
        passed: bool,
        duration_ms: float,
        error_msg: Optional[str] = None,
        trace: Optional[str] = None,
    ):
        self.test_info = test_info
        self.passed = passed
        self.duration_ms = duration_ms
        self.error_msg = error_msg
        self.trace = trace


def discover_tests(tier_filter: str = "all", feature_filter: Optional[str] = None) -> List[TestCaseInfo]:
    """Discover all test functions in selected tiers and modules."""
    test_cases: List[TestCaseInfo] = []

    target_tiers = ["1", "2", "3", "4"] if tier_filter == "all" else [tier_filter]

    for tier in target_tiers:
        modules = TIER_MODULES.get(tier, [])
        for mod_name in modules:
            try:
                mod = importlib.import_module(mod_name)
            except Exception as e:
                print(f"[ERROR] Failed to import {mod_name}: {e}", file=sys.stderr)
                continue

            for name, func in inspect.getmembers(mod, inspect.isfunction):
                if name.startswith("test_"):
                    info = TestCaseInfo(tier, mod_name, name, func)
                    if feature_filter and feature_filter.lower() not in info.feature.lower() and feature_filter.lower() not in info.test_name.lower():
                        continue
                    test_cases.append(info)

    return test_cases


def run_single_test(test_info: TestCaseInfo, client: E2EClient, timeout_sec: float) -> TestResult:
    """Execute a single test with timeout protection."""
    start_time = time.perf_counter()

    def target():
        # Call test function passing the client
        sig = inspect.signature(test_info.test_func)
        if len(sig.parameters) >= 1:
            test_info.test_func(client)
        else:
            test_info.test_func()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(target)
        try:
            future.result(timeout=timeout_sec)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return TestResult(test_info, passed=True, duration_ms=elapsed_ms)
        except FuturesTimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return TestResult(
                test_info,
                passed=False,
                duration_ms=elapsed_ms,
                error_msg=f"Test timed out after {timeout_sec}s",
            )
        except AssertionError as ae:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return TestResult(
                test_info,
                passed=False,
                duration_ms=elapsed_ms,
                error_msg=str(ae) or "AssertionError",
                trace=traceback.format_exc(),
            )
        except Exception as ex:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return TestResult(
                test_info,
                passed=False,
                duration_ms=elapsed_ms,
                error_msg=f"{type(ex).__name__}: {ex}",
                trace=traceback.format_exc(),
            )


def format_table_row(col1: str, col2: str, col3: str, col4: str, widths: Tuple[int, int, int, int]) -> str:
    return f"  {col1.ljust(widths[0])} | {col2.ljust(widths[1])} | {col3.ljust(widths[2])} | {col4.rjust(widths[3])}"


def main() -> int:
    parser = argparse.ArgumentParser(description="SkopaqTrader E2E Test Runner")
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Execution mode: 'mock' (in-process) or 'live' (network)",
    )
    parser.add_argument(
        "--tier",
        choices=["all", "1", "2", "3", "4"],
        default="all",
        help="Tier selection (default: all)",
    )
    parser.add_argument(
        "--feature",
        type=str,
        default=None,
        help="Optional filter for specific feature (e.g. trades, analysis, safety)",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default="http://localhost:8000",
        help="Backend base URL for live mode",
    )
    parser.add_argument(
        "--frontend-url",
        type=str,
        default="http://localhost:3000",
        help="Frontend base URL for live mode",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-test timeout in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed execution output per test",
    )
    parser.add_argument(
        "--json-report",
        type=str,
        default=None,
        help="Optional path to output JSON test execution report",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("  SKOPAQTRADER END-TO-END (E2E) TEST RUNNER")
    print(f"  Mode: {args.mode.upper()} | Tier: {args.tier.upper()} | Feature Filter: {args.feature or 'None'}")
    print(f"  Backend: {args.backend_url} | Frontend: {args.frontend_url}")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    # Discover tests
    tests = discover_tests(tier_filter=args.tier, feature_filter=args.feature)
    if not tests:
        print("[WARNING] No tests matched the specified filters!")
        return 0

    print(f"Discovered {len(tests)} test cases across target tiers.\n")

    # Initialize client
    client = E2EClient(
        mode=args.mode,
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        timeout=args.timeout,
    )

    results: List[TestResult] = []
    failures: List[TestResult] = []
    suite_start = time.perf_counter()

    for idx, test_info in enumerate(tests, 1):
        if args.verbose:
            print(f"[{idx}/{len(tests)}] Running Tier {test_info.tier}::{test_info.test_name}...", end=" ", flush=True)

        res = run_single_test(test_info, client, timeout_sec=args.timeout)
        results.append(res)

        if not res.passed:
            failures.append(res)
            if args.verbose:
                print(f"FAILED ({res.duration_ms:.1f}ms) -> {res.error_msg}")
            else:
                print(f"F", end="", flush=True)
        else:
            if args.verbose:
                print(f"PASSED ({res.duration_ms:.1f}ms)")
            else:
                print(f".", end="", flush=True)

    client.close()
    suite_duration = time.perf_counter() - suite_start
    print("\n")

    # Summary Statistics
    total_count = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(failures)

    # Tier Breakdown
    tier_stats: Dict[str, Dict[str, int]] = {}
    for r in results:
        t = r.test_info.tier
        if t not in tier_stats:
            tier_stats[t] = {"total": 0, "passed": 0, "failed": 0}
        tier_stats[t]["total"] += 1
        if r.passed:
            tier_stats[t]["passed"] += 1
        else:
            tier_stats[t]["failed"] += 1

    widths = (32, 10, 10, 12)
    sep_line = "  " + "-" * (sum(widths) + 9)

    print("=" * 80)
    print("  E2E TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(format_table_row("Test Tier", "Total", "Passed", "Pass Rate", widths))
    print(sep_line)

    tier_labels = {
        "1": "Tier 1: Feature Coverage",
        "2": "Tier 2: Boundary & Corner",
        "3": "Tier 3: Cross-Feature",
        "4": "Tier 4: Real-World Scenarios",
    }

    for t in sorted(tier_stats.keys()):
        stats = tier_stats[t]
        label = tier_labels.get(t, f"Tier {t}")
        rate = f"{(stats['passed']/stats['total'])*100.0:.1f}%"
        print(format_table_row(label, str(stats["total"]), str(stats["passed"]), rate, widths))

    print(sep_line)
    total_rate = f"{(passed_count/total_count)*100.0:.1f}%"
    print(format_table_row("TOTAL SUITE", str(total_count), str(passed_count), total_rate, widths))
    print("=" * 80)
    print(f"  Duration: {suite_duration:.2f}s | Mode: {args.mode} | Exit Code: {0 if failed_count == 0 else 1}")

    # Detail Failures if any
    if failures:
        print("\n" + "!" * 80)
        print(f"  FAILURES ENCOUNTERED ({len(failures)}):")
        print("!" * 80)
        for f in failures:
            print(f"\n[FAIL] Tier {f.test_info.tier} :: {f.test_info.module_name} :: {f.test_info.test_name}")
            print(f"Error: {f.error_msg}")
            if f.trace and args.verbose:
                print(f.trace)

    # Export JSON report if requested
    if args.json_report:
        report_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "suite_duration_seconds": round(suite_duration, 3),
            "summary": {
                "total": total_count,
                "passed": passed_count,
                "failed": failed_count,
                "pass_rate_pct": round((passed_count / total_count) * 100.0, 2),
            },
            "tier_breakdown": tier_stats,
            "results": [
                {
                    "tier": r.test_info.tier,
                    "module": r.test_info.module_name,
                    "feature": r.test_info.feature,
                    "test": r.test_info.test_name,
                    "passed": r.passed,
                    "duration_ms": round(r.duration_ms, 2),
                    "error": r.error_msg,
                }
                for r in results
            ],
        }
        try:
            with open(args.json_report, "w", encoding="utf-8") as jf:
                json.dump(report_data, jf, indent=2)
            print(f"\nJSON test report exported to: {args.json_report}")
        except Exception as e:
            print(f"\n[ERROR] Failed to write JSON report: {e}", file=sys.stderr)

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
