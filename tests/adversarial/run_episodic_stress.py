"""Adversarial Stress Test and Empirical Benchmark Suite for SkopaqTrader Episodic Memory.

Covers:
1. Extreme corpus scaling (up to 10,000 situations) with latency, throughput, and memory profiling.
2. Degenerate query fuzzing (empty, whitespace, punctuation, non-ASCII/Unicode, 10,000-token queries).
3. Boundary inputs (0 situations, 1 situation, 1,000 identical duplicates, 0-word documents).
4. Recency decay stress (10 years past, future timestamps, epoch start, zero-division guards).
5. In-place mutation fuzzing (array mismatch, direct property mutation, index consistency).
6. Multi-threaded concurrency stress testing.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import json
import math
import os
from pathlib import Path
import random
import string
import sys
import time
import tracemalloc
from typing import Any

from skopaq.memory.episodic import (
    EpisodicLessonMatch,
    EpisodicLessonStore,
    InvertedIndex,
    LessonRecord,
)

VOCABULARY = [
    "nifty", "banknifty", "reliance", "tcs", "infy", "hdfc", "icici", "itc", "sbi", "bharti",
    "breakout", "breakdown", "pullback", "reversal", "consolidation", "squeeze", "expansion",
    "support", "resistance", "pivot", "vwap", "supertrend", "bollinger", "ema", "sma",
    "rsi", "macd", "divergence", "overbought", "oversold", "momentum", "trend",
    "bullish", "bearish", "neutral", "volatility", "atr", "slippage", "liquidity",
    "gap", "gapup", "gapdown", "volume", "spike", "exhaustion", "accumulation", "distribution",
    "stoploss", "target", "trailing", "hedging", "options", "futures", "intraday", "swing"
]

ADVICE_TEMPLATES = [
    "Tighten trailing stop-loss to 1.5 ATR and take 50% profit immediately.",
    "Do not chase breakout; wait for retest of broken resistance now acting as support.",
    "Hedge delta exposure using weekly far OTM put options.",
    "Scale out 30% of position size due to bearish RSI divergence on higher timeframe.",
    "Enter long position on 5-minute candle close above VWAP with stop below session low.",
    "Immediate exit: heavy institutional distribution detected at key resistance.",
    "Reduce leverage by 50% during impending macroeconomic release.",
    "Add to winning position on confirmed volume expansion above multi-day pivot.",
]


def generate_synthetic_situation(idx: int, word_count: int = 15) -> str:
    """Generate deterministic synthetic market situation."""
    rng = random.Random(idx * 7919)
    words = [rng.choice(VOCABULARY) for _ in range(word_count)]
    return f"Situation {idx}: " + " ".join(words)


def generate_synthetic_advice(idx: int) -> str:
    return ADVICE_TEMPLATES[idx % len(ADVICE_TEMPLATES)]


def run_benchmark_suite() -> dict[str, Any]:
    print("=" * 80)
    print("  EMPIRICAL ADVERSARIAL STRESS SUITE: EPISODIC LESSON STORE")
    print("=" * 80)

    report: dict[str, Any] = {
        "timestamp": time.time(),
        "platform": sys.platform,
        "python_version": sys.version,
        "benchmarks": {},
    }

    # =========================================================================
    # 1. EXTREME CORPUS SCALING (100 -> 1,000 -> 5,000 -> 10,000)
    # =========================================================================
    print("\n--- 1. Extreme Corpus Scaling (100 to 10,000 Situations) ---")
    corpus_results = []
    test_sizes = [100, 1000, 5000, 10000]

    for size in test_sizes:
        gc.collect()
        tracemalloc.start()
        start_mem = tracemalloc.get_traced_memory()[0]

        store = EpisodicLessonStore(name=f"scale_{size}")

        # Generate data
        situations = [
            (generate_synthetic_situation(i), generate_synthetic_advice(i))
            for i in range(size)
        ]
        timestamps = [
            time.time() - (size - i) * 3600.0  # Spaced over hours
            for i in range(size)
        ]
        meta = [{"timestamp": ts, "id": i} for i, ts in enumerate(timestamps)]

        # Indexing benchmark
        t0 = time.perf_counter()
        store.add_situations(situations, metadata=meta)
        indexing_time = (time.perf_counter() - t0) * 1000.0

        # Memory footprint
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        net_memory_mb = (peak_mem - start_mem) / (1024 * 1024)

        # Rebuild benchmark
        t0 = time.perf_counter()
        store._rebuild_index()
        rebuild_time = (time.perf_counter() - t0) * 1000.0

        # Latency tests (Warmup + 100 query runs)
        queries = [
            "breakout pullback vwap support",
            "nifty reliance rsi divergence overbought",
            "banknifty heavy volume exhaustion gap",
            "supertrend atr trailing stoploss",
            "bearish reversal breakdown resistance",
        ]

        latencies = []
        for _ in range(20):
            for q in queries:
                t_start = time.perf_counter()
                matches = store.get_memories(q, n_matches=5, recency_weight=0.25)
                t_end = time.perf_counter()
                latencies.append((t_end - t_start) * 1000.0)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        max_lat = latencies[-1]
        min_lat = latencies[0]

        meets_latency_sla = max_lat < 50.0

        res_entry = {
            "size": size,
            "indexing_time_ms": round(indexing_time, 2),
            "rebuild_time_ms": round(rebuild_time, 2),
            "memory_peak_mb": round(net_memory_mb, 2),
            "latency_p50_ms": round(p50, 3),
            "latency_p95_ms": round(p95, 3),
            "latency_p99_ms": round(p99, 3),
            "latency_max_ms": round(max_lat, 3),
            "latency_min_ms": round(min_lat, 3),
            "latency_sla_passed": meets_latency_sla,
        }
        corpus_results.append(res_entry)

        status_str = "PASS" if meets_latency_sla else "FAIL"
        print(f"  [{status_str}] Corpus {size:>5} docs: Index {indexing_time:>7.1f}ms | Rebuild {rebuild_time:>6.1f}ms | "
              f"RAM {net_memory_mb:>5.2f}MB | Latency: p50={p50:>5.2f}ms, p95={p95:>5.2f}ms, max={max_lat:>5.2f}ms")

    report["benchmarks"]["corpus_scaling"] = corpus_results

    # =========================================================================
    # 2. DEGENERATE QUERIES (EMPTY, PUNCTUATION, NON-ASCII, 10,000 TOKENS)
    # =========================================================================
    print("\n--- 2. Degenerate Query Fuzzing ---")
    store = EpisodicLessonStore(name="degenerate_test")
    store.add_situations([
        ("NIFTY 50 breakout above 25000 with heavy volume and RSI overbought", "Take partial profits at resistance"),
        ("BankNifty gap down breakdown below 50000 pivot level", "Buy hedge put options immediately"),
        ("TCS consolidating near 200 EMA with low volatility", "Wait for breakout before entry"),
    ])

    degenerate_queries = [
        ("empty_string", "", 0),
        ("whitespace_spaces", "      ", 0),
        ("whitespace_tabs_newlines", "\t\t\n\r\n   \t", 0),
        ("punctuation_ascii", "!@#$%^&*()_+-=[]{}|;':\",.<>/?`~", 0),
        ("pure_non_ascii_devanagari", "निफ्टी ब्रेकआउट रणनीति भारतीय बाजार", 0),
        ("mixed_devanagari_ascii_digits", "निफ्टी 50 ब्रेकआउट रणनीति", 1),
        ("non_ascii_cjk", "日経平均株価 急落 売り 買い シグナル", 0),
        ("non_ascii_emoji", "🚀📈💰📉🔥⚡️🎯📊", 0),
        ("currency_symbols", "₹ $ € £ ¥ ₿", 0),
        ("control_chars", "\x00\x01\x02\x07\x08\x0b\x0c\x0e\x1b\x7f", 0),
        ("single_char_punctuation", ".", 0),
        ("repetitive_10k_tokens", "breakout " * 10000, 1),  # Should match breakout
        ("unique_10k_tokens", " ".join(f"token_{i}" for i in range(10000)), 0),
        ("mixed_10k_tokens_with_nifty", " ".join(f"filler_{i}" for i in range(9999)) + " nifty", 1),
    ]

    degen_results = []
    for name, q, expected_min_matches in degenerate_queries:
        t0 = time.perf_counter()
        try:
            matches = store.get_memories(q, n_matches=3)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            passed = (len(matches) >= expected_min_matches) if expected_min_matches > 0 else (len(matches) == 0)
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name:<30} returned {len(matches)} matches in {elapsed_ms:6.2f}ms")
            degen_results.append({
                "test": name,
                "query_length": len(q),
                "matches_returned": len(matches),
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": passed,
                "error": None,
            })
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            print(f"  [CRASH] {name:<30} raised exception: {exc}")
            degen_results.append({
                "test": name,
                "query_length": len(q),
                "matches_returned": 0,
                "elapsed_ms": round(elapsed_ms, 3),
                "passed": False,
                "error": str(exc),
            })

    report["benchmarks"]["degenerate_queries"] = degen_results

    # =========================================================================
    # 3. BOUNDARY INPUTS (0 DOCS, 1 DOC, 1,000 IDENTICAL, 0-WORD DOCS)
    # =========================================================================
    print("\n--- 3. Boundary Condition Tests ---")
    boundary_results = []

    # 3.1: Zero situations in store
    store_zero = EpisodicLessonStore(name="zero_store")
    assert store_zero.get_memories("breakout") == []
    store_zero._rebuild_index()
    assert store_zero._index.total_docs == 0
    store_zero.clear()
    d = store_zero.to_dict()
    restored_zero = EpisodicLessonStore.from_dict(d)
    assert len(restored_zero.documents) == 0
    boundary_results.append({"name": "zero_documents", "passed": True})
    print("  [PASS] Zero documents: query, rebuild, clear, roundtrip all safe.")

    # 3.2: Exactly 1 situation
    store_one = EpisodicLessonStore(name="one_store")
    store_one.add_situations([("Only single situation in memory", "Single advice")])
    m_match = store_one.get_memories("single situation", n_matches=10)
    assert len(m_match) == 1
    assert m_match[0].recommendation == "Single advice"
    m_nomatch_strict = store_one.get_memories("completely unrelated query", min_lexical_overlap=True)
    assert len(m_nomatch_strict) == 0
    m_nomatch_recency = store_one.get_memories("completely unrelated query", min_lexical_overlap=False)
    assert len(m_nomatch_recency) == 1
    boundary_results.append({"name": "single_document", "passed": True})
    print("  [PASS] Single document: match, non-match strict, non-match fallback safe.")

    # 3.3: 1,000 identical duplicate situations
    store_dups = EpisodicLessonStore(name="dup_store")
    now = time.time()
    dup_sits = [("Identical situation breakout", f"Advice version {i}") for i in range(1000)]
    dup_meta = [{"timestamp": now - (1000 - i) * 60.0} for i in range(1000)]
    store_dups.add_situations(dup_sits, metadata=dup_meta)
    assert len(store_dups.documents) == 1000
    # Assert newest is ranked first due to recency
    top_dup = store_dups.get_memories("Identical situation breakout", n_matches=5, recency_weight=0.5)
    assert len(top_dup) == 5
    assert top_dup[0].recommendation == "Advice version 999"  # Most recent
    assert top_dup[1].recommendation == "Advice version 998"
    boundary_results.append({"name": "1000_identical_duplicates", "passed": True})
    print("  [PASS] 1,000 identical duplicates: correctly ordered by recency.")

    # 3.4: Documents with 0 words
    store_empty_docs = EpisodicLessonStore(name="empty_docs_store")
    store_empty_docs.add_situations([
        ("", "Advice for empty"),
        ("    ", "Advice for spaces"),
        ("!@#$%", "Advice for punctuation"),
        ("₹ ₹ 🚀", "Advice for symbols"),
        ("Valid situation with words", "Valid advice"),
    ])
    assert len(store_empty_docs.documents) == 5
    assert store_empty_docs._index.total_docs == 5
    assert store_empty_docs._index.doc_lens[0] == 0
    assert store_empty_docs._index.doc_lens[1] == 0
    assert store_empty_docs._index.doc_lens[2] == 0
    assert store_empty_docs._index.doc_lens[3] == 0
    assert store_empty_docs._index.doc_lens[4] == 4

    m_valid = store_empty_docs.get_memories("Valid situation", n_matches=2)
    assert len(m_valid) == 1
    assert m_valid[0].recommendation == "Valid advice"
    boundary_results.append({"name": "zero_word_documents", "passed": True})
    print("  [PASS] Zero-word documents: indexed without division errors, filtered cleanly.")

    report["benchmarks"]["boundary_tests"] = boundary_results

    # =========================================================================
    # 4. RECENCY DECAY STRESS (EXTREME PAST, FUTURE, DIVISION-BY-ZERO)
    # =========================================================================
    print("\n--- 4. Recency Decay & Mathematical Robustness Stress ---")
    recency_results = []
    store_rec = EpisodicLessonStore(name="recency_stress", recency_lambda=0.05)
    now = time.time()

    stress_situations = [
        ("Breakout lesson ancient", "Ancient advice", now - 10 * 365 * 86400.0),    # 10 years ago
        ("Breakout lesson epoch", "Epoch advice", 1.0),                             # 1970
        ("Breakout lesson negative_ts", "Negative ts advice", -86400.0),            # Pre-1970
        ("Breakout lesson zero_ts", "Zero ts advice", 0.0),                         # 0.0 fallback
        ("Breakout lesson recent", "Recent advice", now - 60.0),                    # 1 min ago
        ("Breakout lesson future_1d", "Future 1d advice", now + 86400.0),           # +1 day
        ("Breakout lesson future_10y", "Future 10y advice", now + 10 * 365 * 86400.0), # +10 years
    ]

    store_rec.add_situations(
        [(s, a) for s, a, _ in stress_situations],
        metadata=[{"timestamp": ts} for _, _, ts in stress_situations],
    )

    # Query all matches
    matches = store_rec.get_memories("Breakout lesson", n_matches=10, recency_weight=0.5)
    assert len(matches) == 7
    # Verify all scores are finite and in [0, 1]
    for m in matches:
        assert not math.isnan(m.score), f"Score is NaN: {m}"
        assert not math.isinf(m.score), f"Score is Inf: {m}"
        assert 0.0 <= m.score <= 1.05, f"Score out of range: {m.score}"
        assert 0.0 <= m.recency_factor <= 1.0, f"Recency factor out of bounds: {m.recency_factor}"

    # Division-by-zero parameter edge cases
    param_cases = [
        ("recency_weight=0.0", {"recency_weight": 0.0}),
        ("recency_weight=1.0", {"recency_weight": 1.0}),
        ("recency_weight=-0.5", {"recency_weight": -0.5}),
        ("recency_weight=1.5", {"recency_weight": 1.5}),
        ("n_matches=0", {"n_matches": 0}),
        ("n_matches=-5", {"n_matches": -5}),
        ("recency_lambda=0.0", {}),
    ]

    for label, kwargs in param_cases:
        if "recency_lambda" in label:
            s_zero_lam = EpisodicLessonStore(recency_lambda=0.0)
            s_zero_lam.add_situations([("Situation A", "Advice A")])
            res = s_zero_lam.get_memories("Situation A", n_matches=1)
            assert len(res) == 1
            assert abs(res[0].recency_factor - 1.0) < 1e-6
        else:
            res = store_rec.get_memories("Breakout lesson", **kwargs)
            expected_empty = kwargs.get("n_matches", 1) <= 0
            assert (len(res) == 0) if expected_empty else (len(res) > 0)
        recency_results.append({"case": label, "passed": True})
        print(f"  [PASS] Parameter stress: {label}")

    report["benchmarks"]["recency_stress"] = recency_results

    # =========================================================================
    # 5. IN-PLACE MUTATION FUZZING & CONSISTENCY ASSERTIONS
    # =========================================================================
    print("\n--- 5. In-Place Mutation Fuzzing ---")
    fuzz_results = []
    store_fuzz = EpisodicLessonStore(name="fuzz_store")

    # 5.1 Direct array assignment followed by _rebuild_index()
    store_fuzz.documents = ["Alpha breakout", "Beta breakdown", "Gamma reversal"]
    store_fuzz.recommendations = ["Rec alpha", "Rec beta", "Rec gamma"]
    store_fuzz._rebuild_index()

    assert len(store_fuzz.documents) == 3
    assert len(store_fuzz.recommendations) == 3
    assert store_fuzz._index.total_docs == 3
    assert len(store_fuzz._records) == 3
    res_alpha = store_fuzz.get_memories("Alpha breakout", n_matches=1)
    assert len(res_alpha) == 1
    assert res_alpha[0].recommendation == "Rec alpha"
    fuzz_results.append({"name": "standard_in_place_assignment", "passed": True})
    print("  [PASS] Standard in-place assignment + rebuild: fully consistent.")

    # 5.2 Mismatched array lengths (simulate corrupt state before rebuild)
    store_fuzz.documents = ["Doc 1", "Doc 2", "Doc 3", "Doc 4", "Doc 5"]
    store_fuzz.recommendations = ["Rec 1", "Rec 2"]
    # Internal _records synchronizes to common length (2)
    assert len(store_fuzz._records) == 2
    store_fuzz._rebuild_index()
    # Now query: should not crash with IndexError
    res_mismatch = store_fuzz.get_memories("Doc 1", n_matches=5)
    assert len(res_mismatch) > 0
    fuzz_results.append({"name": "mismatched_lengths_docs_longer", "passed": True})
    print("  [PASS] Mismatched lengths (docs > recs): no IndexError, safe retrieval.")

    # 5.3 500-step randomized fuzzing harness
    rng = random.Random(42)
    store_fuzz_active = EpisodicLessonStore(name="fuzz_active")
    fuzz_steps = 500
    errors = []

    for step in range(fuzz_steps):
        op = rng.choice(["add", "mutate_docs", "mutate_recs", "rebuild", "query", "clear", "roundtrip"])
        try:
            if op == "add":
                count = rng.randint(1, 5)
                sits = [(f"Fuzz sit {rng.randint(0, 100)} {rng.choice(VOCABULARY)}", f"Fuzz adv {step}") for _ in range(count)]
                store_fuzz_active.add_situations(sits)
            elif op == "mutate_docs":
                current_len = len(store_fuzz_active.documents)
                new_docs = [f"Direct doc {i} {rng.choice(VOCABULARY)}" for i in range(rng.randint(0, max(1, current_len + 2)))]
                store_fuzz_active.documents = new_docs
            elif op == "mutate_recs":
                current_len = len(store_fuzz_active.recommendations)
                new_recs = [f"Direct rec {i}" for i in range(rng.randint(0, max(1, current_len + 2)))]
                store_fuzz_active.recommendations = new_recs
            elif op == "rebuild":
                store_fuzz_active._rebuild_index()
            elif op == "query":
                q = rng.choice(VOCABULARY) + " " + rng.choice(VOCABULARY)
                k = rng.randint(-1, 10)
                alpha = rng.uniform(-0.2, 1.2)
                _ = store_fuzz_active.get_memories(q, n_matches=k, recency_weight=alpha)
            elif op == "clear":
                store_fuzz_active.clear()
            elif op == "roundtrip":
                d = store_fuzz_active.to_dict()
                restored = EpisodicLessonStore.from_dict(d)
                assert len(restored.documents) == len(store_fuzz_active.documents)
        except Exception as exc:
            errors.append(f"Step {step} op {op} failed: {exc}")

    fuzz_passed = len(errors) == 0
    fuzz_results.append({
        "name": "500_step_randomized_fuzzing",
        "passed": fuzz_passed,
        "error_count": len(errors),
        "errors": errors[:5],
    })
    print(f"  [{'PASS' if fuzz_passed else 'FAIL'}] 500-step randomized fuzz harness: {len(errors)} errors.")

    report["benchmarks"]["mutation_fuzzing"] = fuzz_results

    # =========================================================================
    # 6. MULTI-THREADED CONCURRENCY STRESS
    # =========================================================================
    print("\n--- 6. Multi-Threaded Concurrency Stress (20 Threads, 2,000 Ops) ---")
    store_concurrent = EpisodicLessonStore(name="concurrent_store")
    # Pre-populate with 200 situations
    store_concurrent.add_situations([
        (generate_synthetic_situation(i), generate_synthetic_advice(i))
        for i in range(200)
    ])

    concurrency_errors = []
    num_threads = 20
    ops_per_thread = 100

    def worker_thread(tid: int) -> int:
        local_rng = random.Random(tid * 31337)
        success_count = 0
        for i in range(ops_per_thread):
            action = local_rng.choice(["read", "write", "rebuild"])
            try:
                if action == "read":
                    term = local_rng.choice(VOCABULARY)
                    matches = store_concurrent.get_memories(term, n_matches=3)
                    success_count += 1
                elif action == "write":
                    store_concurrent.add_situations([
                        (f"Concurrent thread {tid} op {i} {local_rng.choice(VOCABULARY)}", f"Advice from thread {tid}")
                    ])
                    success_count += 1
                elif action == "rebuild":
                    store_concurrent._rebuild_index()
                    success_count += 1
            except Exception as e:
                concurrency_errors.append(f"Thread {tid} op {i} error: {e}")
        return success_count

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_threads) as pool:
        futures = [pool.submit(worker_thread, t) for t in range(num_threads)]
        total_successes = sum(f.result() for f in as_completed(futures))
    concurrency_elapsed = (time.perf_counter() - t0) * 1000.0

    concurrency_passed = len(concurrency_errors) == 0 and total_successes == (num_threads * ops_per_thread)
    print(f"  [{'PASS' if concurrency_passed else 'FAIL'}] Concurrency: {total_successes}/2000 ops succeeded "
          f"in {concurrency_elapsed:.1f}ms ({len(concurrency_errors)} errors)")

    report["benchmarks"]["concurrency_stress"] = {
        "threads": num_threads,
        "ops_per_thread": ops_per_thread,
        "total_ops": num_threads * ops_per_thread,
        "total_successes": total_successes,
        "elapsed_ms": round(concurrency_elapsed, 2),
        "errors": concurrency_errors[:5],
        "passed": concurrency_passed,
    }

    # =========================================================================
    # SUMMARY VERDICT
    # =========================================================================
    print("\n" + "=" * 80)
    all_passed = (
        all(c["latency_sla_passed"] for c in corpus_results) and
        all(d["passed"] for d in degen_results) and
        all(b["passed"] for b in boundary_results) and
        all(r["passed"] for r in recency_results) and
        all(f["passed"] for f in fuzz_results) and
        concurrency_passed
    )
    verdict = "APPROVE" if all_passed else "REQUEST_CHANGES"
    report["verdict"] = verdict
    print(f"  CHALLENGE VERDICT: {verdict}")
    print("=" * 80)

    # Save benchmark json artifact
    out_path = Path("tests/adversarial/episodic_stress_results.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote full benchmark artifact to: {out_path.resolve()}")

    return report


if __name__ == "__main__":
    run_benchmark_suite()
