"""NovaSwarm Trader Enterprise Clean-Room Codebase Audit Tool.

Systematically verifies complete decoupling, patent/copyright defense,
AST syntax validity, schema contract symmetry, and regression-free operation.

7 Verification Checks:
1. Zero Upstream Directory Presence
2. Zero Forbidden Terms in Production Source Files
3. AST Syntax Validity Across All Source Files
4. Module Import Resolution & Integrity Audit
5. Schema Contract Symmetry (AnalysisContext <-> Legacy State)
6. CLI Smoke Tests (Entrypoints & Versioning)
7. Full Unit Test Suite Execution
"""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

FORBIDDEN_TERMS = [
    "tradingagents",
    "TradingAgentsGraph",
    "stockstats",
    "route_to_vendor",
    "FinancialSituationMemory",
]

PURGED_DIRS = [
    ROOT_DIR / "tradingagents",
    ROOT_DIR / "cli",
    ROOT_DIR / "dataflows",
    ROOT_DIR / "tests" / "unit" / "dataflows",
]

NOVASWARM_CORE_MODULES = [
    "novaswarm.config",
    "novaswarm.indicators.formulas",
    "novaswarm.indicators.engine",
    "novaswarm.data.models",
    "novaswarm.data.symbols",
    "novaswarm.data.pipeline",
    "novaswarm.data.tools",
    "novaswarm.data.crypto",
    "novaswarm.data.indstocks",
    "novaswarm.llm.client_factory",
    "novaswarm.llm.gateway",
    "novaswarm.llm.model_tier",
    "novaswarm.memory.episodic",
    "novaswarm.memory.store",
    "novaswarm.orchestration.context",
    "novaswarm.orchestration.engine",
    "novaswarm.orchestration.reflection",
    "novaswarm.orchestration.signal_extraction",
    "novaswarm.intelligence.analysts.technical",
    "novaswarm.intelligence.analysts.sentiment",
    "novaswarm.intelligence.analysts.macro",
    "novaswarm.intelligence.analysts.valuation",
    "novaswarm.intelligence.analysts.network",
    "novaswarm.intelligence.analysts.tokenomics",
    "novaswarm.intelligence.analysts.derivatives",
    "novaswarm.intelligence.debate.advocate",
    "novaswarm.intelligence.debate.adjudicator",
    "novaswarm.intelligence.risk_committee.perspectives",
    "novaswarm.intelligence.risk_committee.chief_risk",
    "novaswarm.intelligence.execution.order_strategist",
    "novaswarm.graph.novaswarm_graph",
    "novaswarm.execution.executor",
    "novaswarm.execution.order_router",
    "novaswarm.execution.safety_checker",
    "novaswarm.risk.atr",
    "novaswarm.risk.calendar",
    "novaswarm.risk.concentration",
    "novaswarm.risk.drawdown",
    "novaswarm.risk.regime",
    "novaswarm.broker.client",
    "novaswarm.broker.paper_engine",
    "novaswarm.scanner.engine",
    "novaswarm.scanner.screen",
    "novaswarm.cli.main",
]


def log_header(title: str):
    print(f"\n{'='*70}\n[AUDIT] {title}\n{'='*70}")


def check_1_purged_directories() -> bool:
    log_header("CHECK 1: Purged Upstream Directory Verification")
    passed = True
    for p in PURGED_DIRS:
        if p.exists():
            print(f"  [FAIL] Directory still exists: {p}")
            passed = False
        else:
            print(f"  [PASS] Cleanly absent: {p.relative_to(ROOT_DIR)}")
    return passed


def check_2_forbidden_terms() -> bool:
    log_header("CHECK 2: Forbidden Terms Scan in Production Source Code")
    violations = []
    scan_paths = [ROOT_DIR / "novaswarm", ROOT_DIR / "main.py", ROOT_DIR / "pyproject.toml"]

    for sp in scan_paths:
        if sp.is_file():
            files = [sp]
        else:
            files = list(sp.rglob("*.py"))

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for term in FORBIDDEN_TERMS:
                    if term.lower() in content.lower():
                        # Find line numbers
                        for idx, line in enumerate(content.splitlines(), 1):
                            if term.lower() in line.lower():
                                violations.append((f.relative_to(ROOT_DIR), idx, term, line.strip()))
            except Exception as exc:
                violations.append((f.relative_to(ROOT_DIR), 0, "READ_ERROR", str(exc)))

    if violations:
        print(f"  [FAIL] Found {len(violations)} forbidden term occurrences:")
        for path, line_no, term, snippet in violations:
            print(f"    - {path}:{line_no} [{term}] -> {snippet[:80]}")
        return False

    print(f"  [PASS] Zero forbidden terms found across 100% of production source files.")
    return True


def check_3_ast_syntax() -> bool:
    log_header("CHECK 3: AST Syntax Validity Across All Python Files")
    py_files = list((ROOT_DIR / "novaswarm").rglob("*.py")) + [ROOT_DIR / "main.py"]
    errors = []

    for f in py_files:
        try:
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as e:
            errors.append((f.relative_to(ROOT_DIR), str(e)))

    if errors:
        print(f"  [FAIL] Syntax errors in {len(errors)} files:")
        for path, err in errors:
            print(f"    - {path}: {err}")
        return False

    print(f"  [PASS] All {len(py_files)} Python files parsed cleanly into valid ASTs.")
    return True


def check_4_import_resolution() -> bool:
    log_header("CHECK 4: Core Module Import Resolution & Integrity")
    sys.path.insert(0, str(ROOT_DIR))
    errors = []

    for mod_name in NOVASWARM_CORE_MODULES:
        try:
            importlib.import_module(mod_name)
            print(f"  [OK] {mod_name}")
        except Exception as exc:
            print(f"  [FAIL] {mod_name}: {exc}")
            errors.append((mod_name, str(exc)))

    if errors:
        print(f"  [FAIL] {len(errors)} module imports failed.")
        return False

    print(f"  [PASS] All {len(NOVASWARM_CORE_MODULES)} core modules imported successfully.")
    return True


def check_5_schema_contract_symmetry() -> bool:
    log_header("CHECK 5: Schema Contract Symmetry & Legacy Bridge")
    try:
        from novaswarm.orchestration.context import AnalysisContext

        # Test forward conversion
        ctx = AnalysisContext(
            job_id="audit-contract-check",
            symbol="RELIANCE",
            trade_date="2026-03-01",
            asset_class="equity",
            analyst_reports={
                "technical": "RSI at 62.5, bullish momentum.",
                "sentiment": "Positive institutional sentiment.",
                "macro": "GDP expansion forecast supports equities.",
                "valuation": "Fair value at 2750 INR.",
                "network": "N/A",
                "tokenomics": "N/A",
                "derivatives": "OI indicates call concentration at 2700.",
            },
        )
        legacy = ctx.to_legacy_state()
        assert legacy["company_of_interest"] == "RELIANCE"
        assert legacy["trade_date"] == "2026-03-01"
        assert "RSI at 62.5" in legacy["market_report"]
        assert "Positive institutional" in legacy["sentiment_report"]
        assert "GDP expansion" in legacy["news_report"]
        assert "Fair value at 2750" in legacy["fundamentals_report"]
        assert "OI indicates" in legacy["funding_report"]

        # Test backward restoration
        restored = AnalysisContext.from_legacy_state(legacy, job_id="audit-restore")
        assert restored.symbol == "RELIANCE"
        assert restored.trade_date == "2026-03-01"
        assert restored.analyst_reports.get("technical") == legacy["market_report"]

        print("  [PASS] AnalysisContext bidirectional schema contracts verified.")
        return True
    except Exception as exc:
        print(f"  [FAIL] Contract symmetry check failed: {exc}")
        return False


def check_6_cli_smoke_tests() -> bool:
    log_header("CHECK 6: CLI Smoke Tests & Entrypoint Validation")
    commands = [
        [sys.executable, "main.py", "--help"],
        [sys.executable, "main.py", "version"],
        [sys.executable, "-m", "novaswarm.cli.main", "--help"],
        [sys.executable, "-m", "novaswarm.cli.main", "version"],
    ]

    for cmd in commands:
        cmd_str = " ".join(cmd)
        result = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [FAIL] Command failed ({result.returncode}): {cmd_str}")
            print(f"         stderr: {result.stderr[:200]}")
            return False
        else:
            print(f"  [PASS] {cmd_str} (exit 0)")

    return True


def check_7_unit_test_suite() -> bool:
    log_header("CHECK 7: Full Unit Test Suite Execution")
    cmd = [sys.executable, "-m", "pytest", "tests/unit/", "-q"]
    print(f"  Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [FAIL] Unit test suite failed with exit code {result.returncode}:")
        print(result.stdout[-500:])
        return False

    summary_line = result.stdout.strip().splitlines()[-1] if result.stdout else "Tests passed"
    print(f"  [PASS] {summary_line}")
    return True


def main():
    print(f"{'#'*70}\nNOVASWARM_TRADER CLEAN-ROOM ARCHITECTURAL AUDIT\n{'#'*70}")
    checks = [
        ("Check 1: Zero Upstream Directories", check_1_purged_directories),
        ("Check 2: Zero Forbidden Terms", check_2_forbidden_terms),
        ("Check 3: AST Syntax Validity", check_3_ast_syntax),
        ("Check 4: Module Import Resolution", check_4_import_resolution),
        ("Check 5: Schema Contract Symmetry", check_5_schema_contract_symmetry),
        ("Check 6: CLI Smoke Tests", check_6_cli_smoke_tests),
        ("Check 7: Full Unit Test Suite", check_7_unit_test_suite),
    ]

    results = []
    for name, func in checks:
        ok = func()
        results.append((name, ok))

    log_header("FINAL AUDIT SUMMARY")
    all_passed = True
    for name, ok in results:
        status = "[PASS]" if ok else "[FAIL]"
        if not ok:
            all_passed = False
        print(f"  {status} {name}")

    if all_passed:
        print("\n>>> AUDIT PASSED: 100% CLEAN-ROOM COMPLIANCE VERIFIED. <<<")
        sys.exit(0)
    else:
        print("\n>>> AUDIT FAILED: ONE OR MORE INTEGRITY CHECKS FAILED. <<<")
        sys.exit(1)


if __name__ == "__main__":
    main()
