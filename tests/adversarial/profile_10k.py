"""Profile latency of get_memories on 10,000 documents."""

from __future__ import annotations
import math
import random
import time
from novaswarm.memory.episodic import EpisodicLessonStore

def profile_10k_query():
    print("Populating 10,000 documents...")
    store = EpisodicLessonStore()
    situations = [
        (f"Situation {i}: NIFTY breakout above 25000 with volume spike and RSI overbought support pivot", f"Advice {i}")
        for i in range(10000)
    ]
    meta = [{"timestamp": time.time() - (10000 - i) * 60.0} for i in range(10000)]
    store.add_situations(situations, metadata=meta)

    # Now profile a query that matches many documents
    query = "NIFTY breakout volume RSI support"

    times_tokenize = []
    times_bm25_score = []
    times_recency = []
    times_combine = []
    times_sort = []
    total_times = []

    for _ in range(10):
        t0 = time.perf_counter()

        # Step 1: Tokenize
        t_tok_start = time.perf_counter()
        q_tokens = store._tokenize(query)
        t_tok_end = time.perf_counter()

        # Step 2: BM25 score
        t_bm_start = time.perf_counter()
        raw_bm25_scores = store._index.score(q_tokens)
        max_bm25 = max(raw_bm25_scores) if raw_bm25_scores and max(raw_bm25_scores) > 0 else 0.0
        t_bm_end = time.perf_counter()

        # Step 3: Recency loop
        t_rec_start = time.perf_counter()
        now = time.time()
        recency_factors = []
        N = len(store._records)
        for idx, rec in enumerate(store._records):
            if rec.timestamp > 0:
                delta_t = max(0.0, (now - rec.timestamp) / 86400.0)
            else:
                delta_t = float((N - 1) - idx)
            decay = math.exp(-store.recency_lambda * delta_t)
            recency_factors.append(decay)
        t_rec_end = time.perf_counter()

        # Step 4: Combine candidates
        t_comb_start = time.perf_counter()
        alpha = 0.25
        candidates = []
        for idx in range(N):
            bm25_raw = raw_bm25_scores[idx]
            if bm25_raw <= 0.0:
                continue
            bm25_norm = (bm25_raw / max_bm25) if max_bm25 > 0.0 else 0.0
            recency_val = recency_factors[idx]
            final_score = (1.0 - alpha) * bm25_norm + alpha * recency_val
            candidates.append((idx, final_score, bm25_norm, recency_val))
        t_comb_end = time.perf_counter()

        # Step 5: Sort
        t_sort_start = time.perf_counter()
        candidates.sort(key=lambda item: item[1], reverse=True)
        t_sort_end = time.perf_counter()

        t_total = time.perf_counter() - t0

        times_tokenize.append((t_tok_end - t_tok_start) * 1000.0)
        times_bm25_score.append((t_bm_end - t_bm_start) * 1000.0)
        times_recency.append((t_rec_end - t_rec_start) * 1000.0)
        times_combine.append((t_comb_end - t_comb_start) * 1000.0)
        times_sort.append((t_sort_end - t_sort_start) * 1000.0)
        total_times.append(t_total * 1000.0)

    print(f"Tokenize:     {sum(times_tokenize)/len(times_tokenize):.3f}ms")
    print(f"BM25 score:   {sum(times_bm25_score)/len(times_bm25_score):.3f}ms")
    print(f"Recency loop: {sum(times_recency)/len(times_recency):.3f}ms")
    print(f"Combine loop: {sum(times_combine)/len(times_combine):.3f}ms")
    print(f"Sort:         {sum(times_sort)/len(times_sort):.3f}ms")
    print(f"Total:        avg={sum(total_times)/len(total_times):.3f}ms, max={max(total_times):.3f}ms")

if __name__ == "__main__":
    profile_10k_query()
