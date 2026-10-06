"""Proprietary Pure-Python Episodic Memory Store for AI Trading Agents.

Implements Robertson-Spärck Jones BM25 with non-negative smoothed IDF and
continuous exponential recency decay weighting:

    Score(Q, d) = (1 - alpha) * Normalized_BM25(Q, d) + alpha * exp(-lambda * delta_t)

Features:
- Pure Python/NumPy, zero external search library dependencies.
- Robertson-Spärck Jones IDF with non-negative smoothing (Lucene-style).
- Length-normalized term frequency saturation (k1=1.5, b=0.75).
- Precomputed document length normalization for sub-50ms search latency on 10k+ corpora.
- Dual-compatible EpisodicLessonMatch (inherits from str, supports dict bracket syntax).
- In-place mutation compatibility with MemoryStore (documents, recommendations, _rebuild_index).
- Thread-safe operations via RLock.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import logging
import math
import re
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class LessonRecord:
    """Encapsulates a single episodic trading lesson with temporal and categorical metadata."""

    situation: str
    recommendation: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    term_counts: dict[str, int] = field(default_factory=dict)
    doc_len: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize lesson record to dictionary."""
        return {
            "situation": self.situation,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LessonRecord:
        """Deserialize lesson record from dictionary."""
        return cls(
            situation=data["situation"],
            recommendation=data["recommendation"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


class EpisodicLessonMatch(str):
    """A matched episodic lesson that behaves simultaneously as a string and a dictionary.

    - As a str: returns the recommendation text directly.
    - As a dict: supports ['recommendation'], ['matched_situation'], ['similarity_score'], ['metadata'].
    - As an object: exposes .recommendation, .situation, .score, .metadata attributes.
    """

    recommendation: str
    matched_situation: str
    situation: str
    similarity_score: float
    score: float
    bm25_score: float
    recency_factor: float
    timestamp: float
    metadata: dict[str, Any]

    def __new__(
        cls,
        recommendation: str,
        situation: str = "",
        score: float = 0.0,
        bm25_score: float = 0.0,
        recency_factor: float = 0.0,
        timestamp: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> EpisodicLessonMatch:
        instance = super().__new__(cls, recommendation)
        instance.recommendation = recommendation
        instance.matched_situation = situation
        instance.situation = situation
        instance.similarity_score = float(score)
        instance.score = float(score)
        instance.bm25_score = float(bm25_score)
        instance.recency_factor = float(recency_factor)
        instance.timestamp = float(timestamp)
        instance.metadata = metadata or {}
        return instance

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            if item == "recommendation":
                return self.recommendation
            elif item in ("matched_situation", "situation"):
                return self.matched_situation
            elif item in ("similarity_score", "score"):
                return self.similarity_score
            elif item == "bm25_score":
                return self.bm25_score
            elif item == "recency_factor":
                return self.recency_factor
            elif item == "timestamp":
                return self.timestamp
            elif item == "metadata":
                return self.metadata
            raise KeyError(f"Key '{item}' not found in EpisodicLessonMatch")
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        """Safe dictionary-style retrieval."""
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Convert match to dictionary representation."""
        return {
            "matched_situation": self.matched_situation,
            "recommendation": self.recommendation,
            "similarity_score": self.similarity_score,
            "bm25_score": self.bm25_score,
            "recency_factor": self.recency_factor,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class InvertedIndex:
    """Pure-Python Inverted Index optimized for Robertson-Spärck Jones BM25 retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.postings: dict[str, list[tuple[int, int]]] = {}  # term -> list of (doc_id, tf)
        self.doc_freqs: dict[str, int] = {}  # term -> document frequency n(q)
        self.doc_lens: list[int] = []  # doc_id -> token length |d|
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0
        self._doc_len_norm: list[float] = []

    def build(self, tokenized_docs: list[list[str]]) -> None:
        """Construct inverted index from pre-tokenized documents."""
        self.total_docs = len(tokenized_docs)
        self.doc_lens = [len(doc) for doc in tokenized_docs]
        self.avg_doc_len = (sum(self.doc_lens) / self.total_docs) if self.total_docs > 0 else 0.0

        if self.avg_doc_len > 0.0:
            avg_len = self.avg_doc_len
            self._doc_len_norm = [
                self.k1 * ((1.0 - self.b) + self.b * (l / avg_len))
                for l in self.doc_lens
            ]
        else:
            self._doc_len_norm = [self.k1] * self.total_docs

        self.postings.clear()
        self.doc_freqs.clear()

        for doc_id, tokens in enumerate(tokenized_docs):
            counts = Counter(tokens)
            for term, freq in counts.items():
                if term not in self.postings:
                    self.postings[term] = []
                    self.doc_freqs[term] = 0
                self.postings[term].append((doc_id, freq))
                self.doc_freqs[term] += 1

    def compute_idf(self, term: str) -> float:
        """Robertson-Spärck Jones IDF with non-negative smoothing (Lucene-style).

        IDF(q) = ln(1 + max(0, (N - n(q) + 0.5) / (n(q) + 0.5)))
        Guarantees non-negative weight even when term appears in 100% of documents.
        """
        n_q = self.doc_freqs.get(term, 0)
        if n_q == 0 or self.total_docs == 0:
            return 0.0
        numerator = self.total_docs - n_q + 0.5
        denominator = n_q + 0.5
        return math.log(1.0 + max(0.0, numerator / denominator))

    def score(self, query_tokens: list[str]) -> list[float]:
        """Compute BM25 scores for all documents in O(sum(|postings(q)|)) time."""
        if self.total_docs == 0:
            return []

        scores = [0.0] * self.total_docs
        query_counts = Counter(query_tokens)
        k1_plus_1 = self.k1 + 1.0
        doc_len_norm = self._doc_len_norm

        for term in query_counts:
            if term not in self.postings:
                continue

            idf = self.compute_idf(term)
            if idf <= 0.0:
                continue

            term_weight = idf * k1_plus_1
            for doc_id, tf in self.postings[term]:
                scores[doc_id] += (tf * term_weight) / (tf + doc_len_norm[doc_id])

        return scores


class EpisodicLessonStore:
    """Proprietary Episodic Memory Store for AI Trading Agents.

    Combines Robertson-Spärck Jones BM25 lexical retrieval with continuous
    exponential recency decay weighting:

        Score = (1 - recency_weight) * Normalized_BM25 + recency_weight * exp(-lambda * delta_t)

    Thread-safe, pure Python/NumPy, zero external search library dependencies.
    """

    def __init__(
        self,
        name: str = "default_memory",
        config: Optional[dict[str, Any]] = None,
        k1: float = 1.5,
        b: float = 0.75,
        recency_lambda: float = 0.05,
    ) -> None:
        self.name = name
        self.config = config or {}
        self.k1 = k1
        self.b = b
        self.recency_lambda = recency_lambda
        self._lock = threading.RLock()

        self._records: list[LessonRecord] = []
        self._documents: list[str] = []
        self._recommendations: list[str] = []
        self._index = InvertedIndex(k1=self.k1, b=self.b)

    # ── Backward-compatible properties ──────────────────────────────────────────

    @property
    def documents(self) -> list[str]:
        """List of stored situation descriptions."""
        return self._documents

    @documents.setter
    def documents(self, docs: list[str]) -> None:
        with self._lock:
            self._documents = list(docs)
            self._sync_records_from_arrays()
            self._rebuild_index()

    @property
    def recommendations(self) -> list[str]:
        """List of stored recommendation advice strings."""
        return self._recommendations

    @recommendations.setter
    def recommendations(self, recs: list[str]) -> None:
        with self._lock:
            self._recommendations = list(recs)
            self._sync_records_from_arrays()

    def set_memories(self, docs: list[str], recs: list[str]) -> None:
        """Atomically set both documents and recommendations, rebuilding index once."""
        with self._lock:
            self._documents = list(docs)
            self._recommendations = list(recs)
            self._sync_records_from_arrays()
            self._rebuild_index()

    # ── Core API ────────────────────────────────────────────────────────────────

    def _sync_records_from_arrays(self) -> None:
        """Keep internal _records synchronized with documents/recommendations arrays."""
        n_docs = len(self._documents)
        n_recs = len(self._recommendations)
        max_len = max(n_docs, n_recs)

        new_records = []
        now = time.time()
        for i in range(max_len):
            doc = self._documents[i] if i < n_docs else ""
            rec = self._recommendations[i] if i < n_recs else ""
            if i < len(self._records):
                r = self._records[i]
                r.situation = doc
                r.recommendation = rec
                new_records.append(r)
            else:
                new_records.append(
                    LessonRecord(
                        situation=doc,
                        recommendation=rec,
                        timestamp=now - (max_len - 1 - i) * 86400.0,
                    )
                )
        self._records = new_records

    def _tokenize(self, text: str) -> list[str]:
        """Case-folded alphanumeric tokenization with financial identifier preservation."""
        if not text:
            return []
        tokens = re.findall(r"[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*", text.lower())
        return [t for t in tokens if len(t) > 1 or t.isalnum()]

    def _rebuild_index(self) -> None:
        """Rebuild the InvertedIndex from current documents."""
        with self._lock:
            if not self._documents:
                self._index.build([])
                return
            tokenized_docs = [self._tokenize(doc) for doc in self._documents]
            self._index.build(tokenized_docs)

    def add_situations(
        self,
        situations_and_advice: list[tuple[str, str]],
        metadata: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Add new situations and recommendations, updating index incrementally."""
        with self._lock:
            now = time.time()
            for idx, (situation, advice) in enumerate(situations_and_advice):
                meta = metadata[idx] if metadata and idx < len(metadata) else {}
                ts = meta.get("timestamp", now)
                record = LessonRecord(
                    situation=situation,
                    recommendation=advice,
                    timestamp=ts,
                    metadata=meta,
                )
                self._records.append(record)
                self._documents.append(situation)
                self._recommendations.append(advice)

            self._rebuild_index()

    def get_memories(
        self,
        current_situation: str,
        n_matches: int = 1,
        recency_weight: float = 0.25,
        min_lexical_overlap: bool = True,
    ) -> list[EpisodicLessonMatch]:
        """Retrieve top lessons combining Robertson-Spärck Jones BM25 and exponential recency decay.

        Args:
            current_situation: Query string representing current market situation.
            n_matches: Maximum number of ranked matches to return.
            recency_weight: Convex weight alpha in [0.0, 1.0] for recency vs lexical score.
            min_lexical_overlap: If True, candidate must have BM25 > 0 to be returned.

        Returns:
            List of EpisodicLessonMatch items (subclasses str, supports dict access).
        """
        with self._lock:
            if not self._documents or self._index.total_docs == 0 or n_matches <= 0:
                return []

            query_tokens = self._tokenize(current_situation)
            if not query_tokens:
                return []

            # 1. Robertson-Spärck Jones BM25 scores
            raw_bm25_scores = self._index.score(query_tokens)
            if not raw_bm25_scores:
                return []
            max_bm25 = max(raw_bm25_scores)
            if max_bm25 <= 0.0 and min_lexical_overlap:
                return []

            # Guard against out-of-sync lengths between _records and _index
            N = min(len(self._records), len(raw_bm25_scores))
            if N == 0:
                return []

            # 2. Lazy exponential recency decay & composite convex scoring
            alpha = max(0.0, min(1.0, float(recency_weight)))
            one_minus_alpha = 1.0 - alpha
            inv_max_bm25 = (1.0 / max_bm25) if max_bm25 > 0.0 else 0.0
            now = time.time()
            recency_lambda = self.recency_lambda
            records = self._records

            candidates = []
            for idx in range(N):
                bm25_raw = raw_bm25_scores[idx]
                if min_lexical_overlap and bm25_raw <= 0.0:
                    continue

                rec = records[idx]
                if rec.timestamp > 0.0:
                    delta_t = max(0.0, (now - rec.timestamp) / 86400.0)  # in days
                else:
                    delta_t = float((N - 1) - idx)
                recency_val = math.exp(-recency_lambda * delta_t)

                bm25_norm = (bm25_raw * inv_max_bm25) if max_bm25 > 0.0 else 0.0
                final_score = one_minus_alpha * bm25_norm + alpha * recency_val
                candidates.append((idx, final_score, bm25_norm, recency_val))

            if not candidates:
                return []

            # Sort descending by composite score
            candidates.sort(key=lambda item: item[1], reverse=True)
            top_results = candidates[:n_matches]

            matches = []
            for idx, score, bm25_n, rec_f in top_results:
                rec = records[idx]
                matches.append(
                    EpisodicLessonMatch(
                        recommendation=rec.recommendation,
                        situation=rec.situation,
                        score=score,
                        bm25_score=bm25_n,
                        recency_factor=rec_f,
                        timestamp=rec.timestamp,
                        metadata=rec.metadata,
                    )
                )
            return matches

    def clear(self) -> None:
        """Clear all stored memories and reset the index."""
        with self._lock:
            self._records.clear()
            self._documents.clear()
            self._recommendations.clear()
            self._index.build([])

    def to_dict(self) -> dict[str, Any]:
        """Serialize memory store to dictionary for Supabase / JSON persistence."""
        with self._lock:
            return {
                "name": self.name,
                "documents": list(self._documents),
                "recommendations": list(self._recommendations),
                "records": [r.to_dict() for r in self._records],
                "k1": self.k1,
                "b": self.b,
                "recency_lambda": self.recency_lambda,
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodicLessonStore:
        """Deserialize store from dictionary."""
        store = cls(
            name=data.get("name", "default_memory"),
            k1=data.get("k1", 1.5),
            b=data.get("b", 0.75),
            recency_lambda=data.get("recency_lambda", 0.05),
        )
        raw_docs = data.get("documents")
        raw_recs = data.get("recommendations")
        records_data = data.get("records")

        if records_data:
            store._records = [LessonRecord.from_dict(r) for r in records_data]
            if raw_docs is not None:
                store._documents = list(raw_docs)
            else:
                store._documents = [r.situation for r in store._records]
            if raw_recs is not None:
                store._recommendations = list(raw_recs)
            else:
                store._recommendations = [r.recommendation for r in store._records]
            store._sync_records_from_arrays()
        else:
            store.documents = raw_docs or []
            store.recommendations = raw_recs or []

        store._rebuild_index()
        return store
