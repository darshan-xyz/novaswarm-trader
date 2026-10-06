"""Unit tests for skopaq.memory.episodic (EpisodicLessonStore).

Verifies Robertson-Spärck Jones BM25 mathematical accuracy, continuous exponential
recency decay, boundary handling, dual-compatibility string subclass, agent node loops,
and clean-room decoupling.
"""

from __future__ import annotations

import math
from pathlib import Path
import time
import pytest

from skopaq.memory.episodic import (
    EpisodicLessonMatch,
    EpisodicLessonStore,
    InvertedIndex,
    LessonRecord,
)


class TestDualCompatibleResult:
    """Tier 1: Tests for EpisodicLessonMatch string subclass."""

    def test_behaves_as_string(self):
        match = EpisodicLessonMatch(
            recommendation="Tighten stop loss to 2 ATR.",
            situation="High volatility breakout failure.",
            score=0.85,
        )
        assert isinstance(match, str)
        assert match == "Tighten stop loss to 2 ATR."
        assert f"Advice: {match}" == "Advice: Tighten stop loss to 2 ATR."
        assert match.startswith("Tighten")
        assert match + "\n" == "Tighten stop loss to 2 ATR.\n"

    def test_behaves_as_dict(self):
        match = EpisodicLessonMatch(
            recommendation="Tighten stop loss to 2 ATR.",
            situation="High volatility breakout failure.",
            score=0.85,
            bm25_score=0.9,
            recency_factor=0.7,
            timestamp=1000.0,
            metadata={"trade_id": "T123"},
        )
        # Bracket access matching upstream agent nodes
        assert match["recommendation"] == "Tighten stop loss to 2 ATR."
        assert match["matched_situation"] == "High volatility breakout failure."
        assert match["situation"] == "High volatility breakout failure."
        assert match["similarity_score"] == 0.85
        assert match["score"] == 0.85
        assert match["bm25_score"] == 0.9
        assert match["recency_factor"] == 0.7
        assert match["timestamp"] == 1000.0
        assert match["metadata"] == {"trade_id": "T123"}
        assert match.get("recommendation") == "Tighten stop loss to 2 ATR."
        assert match.get("missing_key", "default") == "default"

    def test_invalid_key_raises_key_error(self):
        match = EpisodicLessonMatch(recommendation="Rec", situation="Sit", score=0.5)
        with pytest.raises(KeyError):
            _ = match["unknown_key"]

    def test_exposes_attributes(self):
        match = EpisodicLessonMatch(
            recommendation="Rec",
            situation="Sit",
            score=0.92,
        )
        assert match.recommendation == "Rec"
        assert match.situation == "Sit"
        assert match.score == 0.92

    def test_to_dict(self):
        match = EpisodicLessonMatch(
            recommendation="Rec",
            situation="Sit",
            score=0.92,
            bm25_score=0.8,
            recency_factor=0.6,
        )
        d = match.to_dict()
        assert d["matched_situation"] == "Sit"
        assert d["recommendation"] == "Rec"
        assert d["similarity_score"] == 0.92


class TestInvertedIndexAndBM25Math:
    """Tier 3: Tests for Robertson-Spärck Jones BM25 inverted index."""

    def test_non_negative_idf(self):
        """RSJ IDF with smoothing must be >= 0 even when term appears in all docs."""
        index = InvertedIndex(k1=1.5, b=0.75)
        # Term 'market' appears in every document (10 out of 10)
        corpus = [["market", "bull"], ["market", "bear"]] + [["market"]] * 8
        index.build(corpus)
        idf = index.compute_idf("market")
        assert idf >= 0.0

    def test_term_frequency_saturation(self):
        """Higher term frequency increases score sub-linearly (saturation)."""
        index = InvertedIndex(k1=1.5, b=0.75)
        doc1 = ["breakout", "volume", "support", "resistance"]
        doc2 = ["breakout", "breakout", "breakout", "support"]
        doc3 = ["breakout"] * 10
        index.build([doc1, doc2, doc3])

        scores = index.score(["breakout"])
        s1, s2, s3 = scores[0], scores[1], scores[2]
        assert s1 < s2 < s3
        # Diminishing returns: 3x frequency does NOT yield 3x score
        assert s2 / s1 < 3.0
        assert s3 / s2 < 3.0

    def test_document_length_penalty(self):
        """Short document with query term scores higher than verbose document with same term count."""
        index = InvertedIndex(k1=1.5, b=0.75)
        doc_short = ["rsi", "divergence", "overbought"]
        doc_long = ["rsi", "divergence", "overbought"] + ["filler"] * 50
        index.build([doc_short, doc_long])

        scores = index.score(["rsi", "divergence"])
        assert scores[0] > scores[1]  # Short document penalized less by b=0.75

    def test_empty_corpus_score(self):
        index = InvertedIndex(k1=1.5, b=0.75)
        index.build([])
        assert index.score(["test"]) == []


class TestEpisodicLessonStoreFunctionalAndBoundaries:
    """Tier 1 & 2: Tests for EpisodicLessonStore operations and edge cases."""

    def test_add_and_retrieve_memories(self):
        store = EpisodicLessonStore()
        store.add_situations([
            ("Breakout on gap up with heavy volume", "Buy on 15m pullback"),
            ("Breakdown below support with low RSI", "Sell or hedge position"),
        ])
        assert len(store.documents) == 2
        assert len(store.recommendations) == 2

        results = store.get_memories("breakout gap up volume", n_matches=1)
        assert len(results) == 1
        assert "pullback" in results[0].recommendation

    def test_empty_store_query_returns_empty_list(self):
        store = EpisodicLessonStore()
        assert store.get_memories("any situation", n_matches=3) == []

    def test_rebuild_index_on_empty_store(self):
        store = EpisodicLessonStore()
        store._rebuild_index()
        assert store._index.total_docs == 0

    def test_zero_lexical_overlap_returns_empty_when_strict(self):
        store = EpisodicLessonStore()
        store.add_situations([
            ("Bullish moving average golden cross", "Enter long position on retracement"),
        ])
        results = store.get_memories("cryptocurrency blockchain mining", min_lexical_overlap=True)
        assert results == []

    def test_zero_lexical_overlap_returns_recency_when_not_strict(self):
        store = EpisodicLessonStore()
        store.add_situations([
            ("Bullish moving average golden cross", "Enter long position on retracement"),
        ])
        results = store.get_memories("cryptocurrency blockchain mining", min_lexical_overlap=False)
        assert len(results) == 1
        assert results[0].recommendation == "Enter long position on retracement"

    def test_whitespace_and_empty_query(self):
        store = EpisodicLessonStore()
        store.add_situations([("Valid situation", "Valid advice")])
        assert store.get_memories("") == []
        assert store.get_memories("   \t\n  ") == []

    def test_add_empty_situation(self):
        store = EpisodicLessonStore()
        store.add_situations([("", "Do nothing")])
        assert len(store.documents) == 1
        assert store.get_memories("test") == []

    def test_duplicate_situations_handled(self):
        store = EpisodicLessonStore()
        store.add_situations([
            ("Breakout above 200 EMA", "Advice 1"),
            ("Breakout above 200 EMA", "Advice 2"),
        ])
        assert len(store.documents) == 2
        results = store.get_memories("Breakout above 200 EMA", n_matches=2)
        assert len(results) == 2

    def test_n_matches_boundary(self):
        store = EpisodicLessonStore()
        store.add_situations([("Situation A", "Advice A")])
        assert store.get_memories("Situation A", n_matches=0) == []
        assert store.get_memories("Situation A", n_matches=-1) == []
        assert len(store.get_memories("Situation A", n_matches=100)) == 1

    def test_clear_resets_store(self):
        store = EpisodicLessonStore()
        store.add_situations([("Sit", "Adv")])
        assert len(store.documents) == 1
        store.clear()
        assert len(store.documents) == 0
        assert len(store.recommendations) == 0
        assert store.get_memories("Sit") == []

    def test_extreme_and_future_timestamps(self):
        store = EpisodicLessonStore()
        now = time.time()
        store.add_situations(
            [("Old memory", "Old advice"), ("Future memory", "Future advice")],
            metadata=[{"timestamp": 0.0}, {"timestamp": now + 86400.0}],
        )
        results = store.get_memories("Old memory", n_matches=1)
        assert len(results) == 1
        assert results[0].score >= 0.0

    def test_recency_decay_calibration(self):
        store = EpisodicLessonStore(recency_lambda=0.05)
        now = time.time()
        # Add identical text at two different timestamps
        store.add_situations(
            [("Gap up with high volume", "Old lesson"), ("Gap up with high volume", "Recent lesson")],
            metadata=[{"timestamp": now - 30 * 86400.0}, {"timestamp": now}],
        )

        # With recency weighting active, recent lesson ranks top
        results_weighted = store.get_memories("Gap up with high volume", n_matches=2, recency_weight=0.25)
        assert results_weighted[0].recommendation == "Recent lesson"

        # With recency weight = 0, both have identical BM25 scores
        results_pure_bm25 = store.get_memories("Gap up with high volume", n_matches=2, recency_weight=0.0)
        assert abs(results_pure_bm25[0].score - results_pure_bm25[1].score) < 1e-5

    def test_half_life_decay_math(self):
        # Lambda = 0.05 => Half-life = ln(2) / 0.05 = 13.8629 days
        half_life_days = math.log(2) / 0.05
        decay = math.exp(-0.05 * half_life_days)
        assert abs(decay - 0.5) < 1e-6

    def test_in_place_mutation_sync(self):
        """Simulate MemoryStore.load() setting documents and recommendations in place."""
        store = EpisodicLessonStore()
        store.documents = ["New situation 1", "New situation 2"]
        store.recommendations = ["New advice 1", "New advice 2"]
        store._rebuild_index()

        results = store.get_memories("New situation 1", n_matches=1)
        assert len(results) == 1
        assert results[0].recommendation == "New advice 1"

    def test_serialization_roundtrip(self):
        store = EpisodicLessonStore()
        store.add_situations(
            [("Situation A", "Advice A"), ("Situation B", "Advice B")],
            metadata=[{"symbol": "RELIANCE", "pnl": 500}, {"symbol": "INFY", "pnl": -200}],
        )
        data = store.to_dict()
        restored = EpisodicLessonStore.from_dict(data)

        assert restored.documents == store.documents
        assert restored.recommendations == store.recommendations
        assert len(restored._records) == 2
        assert restored._records[0].metadata["symbol"] == "RELIANCE"

        # Verify ranking is identical
        orig_match = store.get_memories("Situation A", n_matches=1)[0]
        rest_match = restored.get_memories("Situation A", n_matches=1)[0]
        assert orig_match.recommendation == rest_match.recommendation
        assert abs(orig_match.score - rest_match.score) < 1e-6

    def test_deserialization_from_legacy_dict(self):
        """Deserialize from schema containing only documents and recommendations."""
        legacy_data = {
            "name": "legacy_store",
            "documents": ["Legacy sit 1", "Legacy sit 2"],
            "recommendations": ["Legacy adv 1", "Legacy adv 2"],
        }
        store = EpisodicLessonStore.from_dict(legacy_data)
        assert len(store.documents) == 2
        results = store.get_memories("Legacy sit 1", n_matches=1)
        assert len(results) == 1
        assert results[0].recommendation == "Legacy adv 1"


class TestAgentConsumerSimulations:
    """Tier 4: Simulates downstream consumer loops."""

    def test_agent_node_memory_loop_compatibility(self):
        """Simulate upstream agent node memory consumption loop."""
        store = EpisodicLessonStore()
        store.add_situations([
            ("Overbought RSI divergence", "Take partial profit"),
            ("Support bounce at 200 EMA", "Add to position"),
        ])

        past_memories = store.get_memories("Overbought RSI", n_matches=2)
        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        assert "Take partial profit" in past_memory_str

    def test_string_list_consumer_compatibility(self):
        store = EpisodicLessonStore()
        store.add_situations([("Situation X", "Advice X")])
        memories = store.get_memories("Situation X", n_matches=1)

        for item in memories:
            assert isinstance(item, str)
            assert item == "Advice X"

    def test_mcp_server_recall_simulation(self):
        store = EpisodicLessonStore()
        store.add_situations([("Situation A", "Advice A"), ("Situation B", "Advice B")])
        matches = store.get_memories("Situation", n_matches=2)
        results = [{"recommendation": m.get("recommendation", ""), "score": m.get("score", 0)} for m in matches]
        assert len(results) == 2
        assert results[0]["recommendation"] != ""


class TestCleanRoomDecoupling:
    """Verifies complete decoupling from rank_bm25 and tradingagents."""

    def test_zero_rank_bm25_in_episodic(self):
        content = Path("skopaq/memory/episodic.py").read_text(encoding="utf-8")
        assert "rank_bm25" not in content
        assert "tradingagents" not in content


class TestEpisodicMemoryEdgeCaseRemediations:
    """Verifies remediation for IndexError and deserialization data loss."""

    def test_get_memories_clamped_iteration_without_rebuild(self):
        """IndexError regression test: len(_records) > _index.total_docs must not raise IndexError."""
        store = EpisodicLessonStore()
        store.add_situations([("Short situation", "Short advice")])
        assert store._index.total_docs == 1

        # Direct mutation without calling _rebuild_index()
        store.documents = ["Sit 1", "Sit 2", "Sit 3"]
        store.recommendations = ["Rec 1", "Rec 2", "Rec 3"]
        assert len(store._records) == 3
        assert store._index.total_docs == 1

        # Querying must clamp iteration to min(3, 1) and not raise IndexError
        results = store.get_memories("Sit 1", n_matches=3)
        assert isinstance(results, list)

    def test_get_memories_when_records_fewer_than_index(self):
        """Inverse boundary test: len(_records) < len(raw_bm25_scores) must not raise IndexError."""
        store = EpisodicLessonStore()
        store.documents = ["Doc 1", "Doc 2", "Doc 3"]
        store.recommendations = ["Rec 1", "Rec 2", "Rec 3"]
        store._rebuild_index()
        assert store._index.total_docs == 3

        # Manually truncate _records to simulate out-of-sync state
        store._records = store._records[:1]
        assert len(store._records) == 1
        assert store._index.total_docs == 3

        # Must not raise IndexError when accessing self._records[idx]
        results = store.get_memories("Doc 1", n_matches=5)
        assert isinstance(results, list)
        assert len(results) <= 1

    def test_deserialization_preserves_documents_when_records_shorter(self):
        """Data loss regression test: from_dict must preserve all documents when len(documents) > len(records)."""
        data = {
            "name": "mismatched_store",
            "documents": ["Situation 1", "Situation 2", "Situation 3"],
            "recommendations": ["Advice 1"],
            "records": [
                {"situation": "Situation 1", "recommendation": "Advice 1", "timestamp": 1000.0, "metadata": {}}
            ],
        }
        store = EpisodicLessonStore.from_dict(data)

        # All 3 documents must be preserved
        assert len(store.documents) == 3
        assert store.documents == ["Situation 1", "Situation 2", "Situation 3"]
        assert len(store._records) == 3
        assert store._records[0].recommendation == "Advice 1"
        assert store._records[1].recommendation == ""
        assert store._records[2].recommendation == ""
        assert store._index.total_docs == 3

    def test_sync_records_from_arrays_preserves_all_documents(self):
        """Array synchronization must handle length discrepancies without dropping documents."""
        store = EpisodicLessonStore()
        store.documents = ["Doc A", "Doc B", "Doc C", "Doc D"]
        store.recommendations = ["Rec A"]

        assert len(store.documents) == 4
        assert len(store._records) == 4
        assert store._records[0].situation == "Doc A"
        assert store._records[0].recommendation == "Rec A"
        assert store._records[1].situation == "Doc B"
        assert store._records[1].recommendation == ""
        assert store._records[2].situation == "Doc C"
        assert store._records[3].situation == "Doc D"

        store._rebuild_index()
        assert store._index.total_docs == 4
        matches = store.get_memories("Doc C", n_matches=1)
        assert len(matches) == 1
        assert matches[0].situation == "Doc C"
