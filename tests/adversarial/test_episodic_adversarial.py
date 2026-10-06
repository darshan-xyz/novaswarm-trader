"""Adversarial stress and boundary correctness test suite for SkopaqTrader Episodic Memory.

Milestone 2 Challenge Suite:
- Extreme corpus scaling (10,000 situations) with strict <50ms query latency SLA.
- Degenerate and adversarial query fuzzing (empty, punctuation, Unicode/Devanagari, 10,000 tokens).
- Boundary conditions (0 docs, 1 doc, identical duplicates, 0-word docs).
- Temporal recency decay extremes (10 years past, future timestamps, division-by-zero guards).
- In-place mutation fuzzing and index synchronization integrity.
- Multi-threaded concurrent read/write stress.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import random
import time
import pytest

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
    "stoploss", "target", "trailing", "hedging", "options", "futures", "intraday", "swing",
]


class TestExtremeCorpusScale:
    """Stress tests on large corpus sizes up to 10,000 items."""

    def test_10000_situations_latency_sla(self):
        """10,000 situations must index cleanly and satisfy < 50ms search latency SLA."""
        store = EpisodicLessonStore(name="benchmark_10k")
        size = 10000

        situations = [
            (f"Situation {i}: " + " ".join([VOCABULARY[i % len(VOCABULARY)], VOCABULARY[(i * 3) % len(VOCABULARY)], "breakout", "support"]),
             f"Recommendation {i} for risk management")
            for i in range(size)
        ]
        now = time.time()
        meta = [{"timestamp": now - (size - i) * 60.0} for i in range(size)]

        t_idx_start = time.perf_counter()
        store.add_situations(situations, metadata=meta)
        indexing_time_ms = (time.perf_counter() - t_idx_start) * 1000.0

        assert len(store.documents) == size
        assert store._index.total_docs == size
        # Indexing 10k items should complete within 5 seconds in pure Python
        assert indexing_time_ms < 5000.0, f"Indexing took {indexing_time_ms}ms (> 5000ms)"

        # Measure query latency over diverse queries
        test_queries = [
            "breakout support",
            "nifty reliance rsi divergence",
            "banknifty non_matching_term",
            "supertrend atr trailing",
        ]

        latencies = []
        for _ in range(5):
            for q in test_queries:
                t0 = time.perf_counter()
                results = store.get_memories(q, n_matches=5, recency_weight=0.25)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(elapsed_ms)
                assert isinstance(results, list)

        max_lat = max(latencies)
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

        # Strict latency SLA: must be < 50ms
        assert max_lat < 50.0, f"Max latency was {max_lat:.2f}ms, exceeding 50ms SLA"
        assert p95_lat < 30.0, f"P95 latency was {p95_lat:.2f}ms"


class TestDegenerateAndAdversarialQueries:
    """Degenerate, empty, non-ASCII, and token-overflow query stress."""

    @pytest.fixture
    def populated_store(self):
        store = EpisodicLessonStore(name="degen_fixture")
        store.add_situations([
            ("NIFTY 50 breakout above 25000 with heavy volume and RSI overbought", "Take partial profits at resistance"),
            ("BankNifty gap down breakdown below 50000 pivot level", "Buy hedge put options immediately"),
            ("TCS consolidating near 200 EMA with low volatility", "Wait for breakout before entry"),
        ])
        return store

    def test_empty_and_whitespace_queries(self, populated_store):
        assert populated_store.get_memories("") == []
        assert populated_store.get_memories(" ") == []
        assert populated_store.get_memories("   \t\r\n   ") == []

    def test_punctuation_only_queries(self, populated_store):
        punct = "!@#$%^&*()_+-=[]{}|;':\",.<>/?`~"
        assert populated_store.get_memories(punct) == []
        assert populated_store.get_memories("...") == []
        assert populated_store.get_memories("---") == []

    def test_pure_non_ascii_and_multilingual_queries(self, populated_store):
        # Pure Devanagari without ASCII numbers yields empty tokens
        assert populated_store.get_memories("निफ्टी ब्रेकआउट रणनीति") == []
        # Chinese / Japanese
        assert populated_store.get_memories("日経平均株価 急落") == []
        # Emoji
        assert populated_store.get_memories("🚀📈💰📉🔥") == []
        # Currency symbols
        assert populated_store.get_memories("₹ $ € £ ¥") == []
        # Control characters
        assert populated_store.get_memories("\x00\x01\x02\x07\x08\x1b\x7f") == []

    def test_mixed_script_with_ascii_digits(self, populated_store):
        # Tokenizer extracts '50' from mixed script and matches 'NIFTY 50'
        matches = populated_store.get_memories("निफ्टी 50 ब्रेकआउट", n_matches=1)
        assert len(matches) == 1
        assert matches[0].recommendation == "Take partial profits at resistance"

    def test_10000_token_queries(self, populated_store):
        # Repetitive 10,000 tokens of matching term
        long_query_matching = "breakout " * 10000
        t0 = time.perf_counter()
        matches = populated_store.get_memories(long_query_matching, n_matches=2)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert len(matches) > 0
        assert elapsed_ms < 100.0

        # Unique 10,000 tokens of non-matching terms
        long_query_unique = " ".join(f"nonmatch_term_{i}" for i in range(10000))
        matches_unique = populated_store.get_memories(long_query_unique)
        assert matches_unique == []


class TestBoundaryCorpora:
    """Boundary sizes and degenerate document contents."""

    def test_empty_store_operations(self):
        store = EpisodicLessonStore(name="empty")
        assert store.get_memories("test") == []
        assert store.documents == []
        assert store.recommendations == []
        store._rebuild_index()
        assert store._index.total_docs == 0
        store.clear()
        d = store.to_dict()
        restored = EpisodicLessonStore.from_dict(d)
        assert len(restored.documents) == 0

    def test_single_document_store(self):
        store = EpisodicLessonStore(name="single")
        store.add_situations([("Sole situation text", "Sole recommendation")])
        # Strict match
        m = store.get_memories("Sole situation", n_matches=10)
        assert len(m) == 1
        assert m[0].recommendation == "Sole recommendation"
        # Strict non-match
        assert store.get_memories("completely unrelated query", min_lexical_overlap=True) == []
        # Non-strict fallback to recency
        m_rec = store.get_memories("completely unrelated query", min_lexical_overlap=False)
        assert len(m_rec) == 1
        assert m_rec[0].recommendation == "Sole recommendation"

    def test_1000_identical_duplicates_recency_sorting(self):
        store = EpisodicLessonStore(name="dups")
        now = time.time()
        sits = [("Identical situation text", f"Advice {i}") for i in range(1000)]
        meta = [{"timestamp": now - (1000 - i) * 10.0} for i in range(1000)]
        store.add_situations(sits, metadata=meta)

        results = store.get_memories("Identical situation", n_matches=5, recency_weight=0.5)
        assert len(results) == 5
        # Advice 999 is newest, must be top
        assert results[0].recommendation == "Advice 999"
        assert results[1].recommendation == "Advice 998"

    def test_zero_word_documents_indexing(self):
        store = EpisodicLessonStore(name="zero_words")
        store.add_situations([
            ("", "Rec for empty string"),
            ("   ", "Rec for spaces"),
            ("!@#$%", "Rec for punctuation"),
            ("₹ 🚀", "Rec for non-ascii symbols"),
            ("Valid equity breakout", "Rec for valid"),
        ])
        assert len(store.documents) == 5
        assert store._index.total_docs == 5
        # Verify average doc length calculation didn't divide by zero
        assert store._index.avg_doc_len > 0.0

        matches = store.get_memories("equity breakout", n_matches=2)
        assert len(matches) == 1
        assert matches[0].recommendation == "Rec for valid"


class TestRecencyDecayAdversarialMath:
    """Stress tests on timestamp calculations and mathematical boundary guards."""

    def test_extreme_past_and_future_timestamps(self):
        store = EpisodicLessonStore(recency_lambda=0.05)
        now = time.time()
        situations = [
            ("Ancient 10yr lesson", "Advice 1", now - 10 * 365 * 86400.0),
            ("Epoch 1970 lesson", "Advice 2", 1.0),
            ("Negative ts lesson", "Advice 3", -86400.0),
            ("Zero ts lesson", "Advice 4", 0.0),
            ("Future 1d lesson", "Advice 5", now + 86400.0),
            ("Future 10yr lesson", "Advice 6", now + 10 * 365 * 86400.0),
        ]
        store.add_situations(
            [(s, a) for s, a, _ in situations],
            metadata=[{"timestamp": ts} for _, _, ts in situations],
        )

        matches = store.get_memories("lesson", n_matches=10, recency_weight=0.5)
        assert len(matches) == 6
        for m in matches:
            assert not math.isnan(m.score)
            assert not math.isinf(m.score)
            assert 0.0 <= m.score <= 1.05
            assert 0.0 <= m.recency_factor <= 1.0

        # Future lessons clamped delta_t=0 => recency_factor=1.0
        future_match = [m for m in matches if "Future 10yr" in m.matched_situation][0]
        assert abs(future_match.recency_factor - 1.0) < 1e-6

        # Ancient lessons decayed heavily
        ancient_match = [m for m in matches if "Ancient 10yr" in m.matched_situation][0]
        assert ancient_match.recency_factor < 1e-10

    def test_division_by_zero_parameter_guards(self):
        store = EpisodicLessonStore()
        store.add_situations([("Valid market pattern", "Valid recommendation")])

        # Bounds outside [0, 1] clamped gracefully
        res_neg = store.get_memories("pattern", recency_weight=-1.0)
        assert len(res_neg) == 1
        res_pos = store.get_memories("pattern", recency_weight=2.0)
        assert len(res_pos) == 1

        # n_matches boundaries
        assert store.get_memories("pattern", n_matches=0) == []
        assert store.get_memories("pattern", n_matches=-10) == []

        # Zero recency lambda
        store_zero_lambda = EpisodicLessonStore(recency_lambda=0.0)
        store_zero_lambda.add_situations([("Situation", "Advice")])
        res_zl = store_zero_lambda.get_memories("Situation", recency_weight=0.5)
        assert len(res_zl) == 1
        assert abs(res_zl[0].recency_factor - 1.0) < 1e-6


class TestInPlaceMutationAndConsistency:
    """Fuzzing in-place mutations of documents/recommendations properties."""

    def test_in_place_assignment_rebuild(self):
        store = EpisodicLessonStore()
        store.documents = ["Doc A", "Doc B", "Doc C"]
        store.recommendations = ["Rec A", "Rec B", "Rec C"]
        store._rebuild_index()

        assert len(store.documents) == 3
        assert len(store.recommendations) == 3
        assert store._index.total_docs == 3
        res = store.get_memories("Doc A", n_matches=1)
        assert len(res) == 1
        assert res[0].recommendation == "Rec A"

    def test_mismatched_array_lengths(self):
        store = EpisodicLessonStore()
        # More documents than recommendations
        store.documents = ["Doc 1", "Doc 2", "Doc 3", "Doc 4"]
        store.recommendations = ["Rec 1", "Rec 2"]
        store._rebuild_index()

        # Should not crash on query
        res = store.get_memories("Doc 1", n_matches=5)
        assert len(res) > 0

        # More recommendations than documents
        store.documents = ["Doc Solo"]
        store.recommendations = ["Rec 1", "Rec 2", "Rec 3"]
        store._rebuild_index()
        res_solo = store.get_memories("Doc Solo", n_matches=5)
        assert len(res_solo) == 1

    def test_serialization_truncation_data_loss(self):
        """Serialization roundtrip must preserve all documents even if recommendations was shorter."""
        store = EpisodicLessonStore()
        store.documents = ["Sit 1", "Sit 2", "Sit 3"]
        store.recommendations = ["Rec 1"]
        store._rebuild_index()

        serialized = store.to_dict()
        restored = EpisodicLessonStore.from_dict(serialized)
        # Bug challenge: currently restored.documents drops Sit 2 and Sit 3!
        assert len(restored.documents) == len(store.documents), (
            f"Data loss! Expected {len(store.documents)} docs, got {len(restored.documents)}"
        )

    def test_randomized_mutation_fuzz_harness(self):
        """Randomized mutation must not crash with unhandled IndexError when querying."""
        rng = random.Random(1337)
        store = EpisodicLessonStore()
        for step in range(200):
            op = rng.choice(["add", "set_docs", "set_recs", "rebuild", "query", "clear"])
            if op == "add":
                store.add_situations([(f"Sit {rng.randint(0, 50)} {rng.choice(VOCABULARY)}", f"Adv {step}")])
            elif op == "set_docs":
                store.documents = [f"Direct {i} {rng.choice(VOCABULARY)}" for i in range(rng.randint(0, 10))]
            elif op == "set_recs":
                store.recommendations = [f"Rec {i}" for i in range(rng.randint(0, 10))]
            elif op == "rebuild":
                store._rebuild_index()
            elif op == "query":
                # Must never raise IndexError: list index out of range
                _ = store.get_memories(rng.choice(VOCABULARY), n_matches=rng.randint(-1, 5))
            elif op == "clear":
                store.clear()


class TestConcurrencySafety:
    """Thread safety under concurrent reader and writer contention."""

    def test_multithreaded_read_write_contention(self):
        store = EpisodicLessonStore(name="concurrent")
        # Seed store
        store.add_situations([
            (f"Initial situation {i} {VOCABULARY[i % len(VOCABULARY)]}", f"Advice {i}")
            for i in range(50)
        ])

        num_threads = 10
        ops_per_thread = 50
        errors = []

        def worker(tid: int):
            rng = random.Random(tid * 997)
            for i in range(ops_per_thread):
                try:
                    action = rng.choice(["read", "write", "rebuild"])
                    if action == "read":
                        _ = store.get_memories(rng.choice(VOCABULARY), n_matches=3)
                    elif action == "write":
                        store.add_situations([(f"Thread {tid} doc {i}", f"Thread {tid} rec")])
                    elif action == "rebuild":
                        store._rebuild_index()
                except Exception as e:
                    errors.append(f"Thread {tid} op {i}: {e}")

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker, t) for t in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0, f"Concurrency errors encountered: {errors}"
