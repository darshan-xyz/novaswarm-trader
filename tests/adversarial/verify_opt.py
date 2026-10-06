"""Verify feasibility of suggested optimizations for EpisodicLessonStore."""

from __future__ import annotations
import math
import time
from collections import Counter

def benchmark_optimized_inner_loop():
    size = 10000
    # Simulate postings for 5 terms in 10,000 docs (worst case: all terms in all docs)
    postings = {
        f"term_{t}": [(i, 1) for i in range(size)]
        for t in range(5)
    }
    doc_lens = [15] * size
    avg_doc_len = 15.0
    k1 = 1.5
    b = 0.75

    # OPTIMIZATION 1: Precompute length norm table during build()
    k1_plus_1 = k1 + 1.0
    len_norm = [k1 * ((1.0 - b) + b * (l / avg_doc_len)) for l in doc_lens]

    # Benchmark optimized score
    t0 = time.perf_counter()
    scores = [0.0] * size
    query_terms = [f"term_{t}" for t in range(5)]
    idfs = [1.2] * 5

    for term, idf in zip(query_terms, idfs):
        idf_k1 = idf * k1_plus_1
        for doc_id, tf in postings[term]:
            scores[doc_id] += (tf * idf_k1) / (tf + len_norm[doc_id])

    t_score = (time.perf_counter() - t0) * 1000.0

    # OPTIMIZATION 2: Lazy recency decay only for top candidates / positive bm25
    t1 = time.perf_counter()
    max_bm25 = max(scores)
    now = time.time()
    alpha = 0.25
    recency_lambda = 0.05

    # Single-pass candidate collection + lazy recency
    candidates = []
    for idx, bm25_raw in enumerate(scores):
        if bm25_raw <= 0:
            continue
        # Only compute exp for non-zero bm25
        delta_t = 1.0
        rec_val = math.exp(-recency_lambda * delta_t)
        bm25_norm = bm25_raw / max_bm25
        final_score = (1.0 - alpha) * bm25_norm + alpha * rec_val
        candidates.append((idx, final_score))

    t_candidates = (time.perf_counter() - t1) * 1000.0

    print(f"Optimized BM25 score time:  {t_score:.2f}ms (was ~52ms)")
    print(f"Optimized single-pass time: {t_candidates:.2f}ms (was ~18ms)")
    print(f"Total optimized latency:    {t_score + t_candidates:.2f}ms (was ~72ms)")

if __name__ == "__main__":
    benchmark_optimized_inner_loop()
