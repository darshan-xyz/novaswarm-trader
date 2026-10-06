"""Empirical runner for adversarial stress testing on SkopaqTrader."""

from __future__ import annotations

import json
import time
from fastapi.testclient import TestClient
from skopaq.api.server import app
from skopaq.api.analysis_manager import AnalysisJobManager, AnalysisJob
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_adversarial_suite():
    client = TestClient(app)
    results = {}

    print("================================================================================")
    print("  RUNNING ADVERSARIAL STRESS SUITE (SKOPAQTRADER LIVE APP)")
    print("================================================================================")

    # 1. Invalid Symbol Formats & Injections
    print("\n--- 1. Boundary & Injection Tests on /api/analysis ---")
    bad_symbols = [
        ("INVALID$$%%^^", "Special characters/symbols"),
        ("TCS'; DROP TABLE trades;--", "SQL Injection pattern"),
        ("<script>alert(1)</script>", "XSS HTML pattern"),
        ("A" * 100, "100-character excessive length"),
        ("   ", "Whitespace only"),
    ]
    sym_results = []
    for sym, desc in bad_symbols:
        resp = client.post("/api/analysis", json={"symbol": sym})
        passed = resp.status_code == 422
        sym_results.append({
            "input": sym,
            "description": desc,
            "status_code": resp.status_code,
            "expected_422": passed,
            "response": resp.json() if resp.status_code != 500 else "Internal Error",
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] {desc}: code {resp.status_code}")
    results["symbol_boundaries"] = sym_results

    # 2. Lookback Days Validation
    print("\n--- 2. Lookback Days Range Tests ---")
    lookbacks = [
        (-5, "Negative days (-5)"),
        (0, "Zero days (0)"),
        (400, "Excessive days (400 > 365)"),
        (30, "Valid lookback (30)"),
    ]
    lb_results = []
    for lb, desc in lookbacks:
        resp = client.post("/api/analysis", json={"symbol": "RELIANCE", "lookback_days": lb})
        expected_code = 202 if lb == 30 else 422
        passed = resp.status_code == expected_code
        lb_results.append({
            "lookback_days": lb,
            "description": desc,
            "status_code": resp.status_code,
            "expected": expected_code,
            "passed": passed,
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] {desc}: got {resp.status_code}, expected {expected_code}")
    results["lookback_boundaries"] = lb_results

    # 3. Concurrent Jobs Stress
    print("\n--- 3. Concurrency Stress on /api/analysis ---")
    t0 = time.perf_counter()
    num_concurrent = 25
    symbols = [f"STRESS_{i:02d}" for i in range(num_concurrent)]

    def post_analysis(s):
        return client.post("/api/analysis", json={"symbol": s})

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(post_analysis, s) for s in symbols]
        responses = [f.result() for f in futures]

    elapsed = time.perf_counter() - t0
    status_codes = [r.status_code for r in responses]
    job_ids = [r.json().get("job_id") for r in responses if r.status_code == 202]
    all_202 = all(c == 202 for c in status_codes)
    unique_ids = len(set(job_ids)) == num_concurrent
    print(f"  Submitted {num_concurrent} jobs in {elapsed:.3f}s")
    print(f"  [{'PASS' if all_202 else 'FAIL'}] All 202 Accepted: {all_202}")
    print(f"  [{'PASS' if unique_ids else 'FAIL'}] Unique Job IDs generated: {len(set(job_ids))}/{num_concurrent}")
    results["concurrency"] = {
        "num_jobs": num_concurrent,
        "elapsed_seconds": elapsed,
        "all_accepted": all_202,
        "unique_job_ids": unique_ids,
    }

    # 4. Rapid Stream Connect/Disconnect Stress
    print("\n--- 4. Rapid Stream Connect/Disconnect Stress ---")
    test_job_resp = client.post("/api/analysis", json={"symbol": "INFY"})
    stress_job_id = test_job_resp.json()["job_id"]
    mgr = AnalysisJobManager.get_instance()
    stress_job = mgr.get_job(stress_job_id)

    num_rapid = 30
    disconnect_errors = 0

    def connect_disconnect():
        try:
            with client.stream("GET", f"/api/analysis/{stress_job_id}/stream") as stream:
                for line in stream.iter_lines():
                    if line:
                        break
        except Exception as e:
            return str(e)
        return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(connect_disconnect) for _ in range(num_rapid)]
        for f in futs:
            err = f.result()
            if err:
                disconnect_errors += 1

    time.sleep(0.3)
    remaining_subscribers = len(stress_job.subscribers)
    print(f"  Performed {num_rapid} rapid connect-disconnect cycles")
    print(f"  Stream abort errors: {disconnect_errors}")
    print(f"  Remaining active subscribers in job: {remaining_subscribers}")
    results["rapid_disconnect"] = {
        "cycles": num_rapid,
        "errors": disconnect_errors,
        "remaining_subscribers": remaining_subscribers,
    }

    # 5. Pre-Trade Safety Boundary Probes
    print("\n--- 5. Pre-Trade Safety Simulation Boundary Stress ---")
    safety_tests = [
        {
            "name": "Negative Price",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 1, "price": -100.0, "stop_loss": 90.0},
            "expect": "HTTP_422",
        },
        {
            "name": "Zero Price",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 1, "price": 0.0, "stop_loss": 90.0},
            "expect": "HTTP_422",
        },
        {
            "name": "Zero Quantity",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 0, "price": 100.0, "stop_loss": 90.0},
            "expect": "HTTP_422",
        },
        {
            "name": "Huge Quantity (1,000,000 shares)",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 1_000_000, "price": 1800.0, "stop_loss": 1700.0},
            "expect": "REJECTED_PASSED_FALSE",
        },
        {
            "name": "Exceeding Max Order Value Ceiling (INR 500,000)",
            "req": {"symbol": "RELIANCE", "action": "BUY", "quantity": 250, "price": 2800.0, "stop_loss": 2700.0}, # 700k
            "expect": "REJECTED_PASSED_FALSE",
        },
        {
            "name": "Inverted Stop-Loss (BUY with stop_loss > entry price)",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 2, "price": 1800.0, "stop_loss": 1850.0},
            "expect": "REJECTED_INVERTED_SL",
        },
        {
            "name": "Inverted Stop-Loss (SELL with stop_loss < entry price)",
            "req": {"symbol": "INFY", "action": "SELL", "quantity": 2, "price": 1800.0, "stop_loss": 1750.0},
            "expect": "REJECTED_INVERTED_SL",
        },
        {
            "name": "Overly Tight Stop-Loss (0.05% < 2% min requirement)",
            "req": {"symbol": "INFY", "action": "BUY", "quantity": 2, "price": 1800.0, "stop_loss": 1799.0},
            "expect": "REJECTED_TIGHT_SL",
        },
    ]

    safety_results = []
    for t in safety_tests:
        r = client.post("/api/safety/simulate", json=t["req"])
        passed = False
        outcome = ""
        if t["expect"] == "HTTP_422":
            passed = r.status_code == 422
            outcome = f"status {r.status_code}"
        else:
            if r.status_code == 200:
                body = r.json()
                sim_passed = body.get("passed")
                rejections = body.get("rejections", [])
                if t["expect"] in ("REJECTED_PASSED_FALSE", "REJECTED_INVERTED_SL", "REJECTED_TIGHT_SL"):
                    passed = (sim_passed is False) and len(rejections) > 0
                outcome = f"passed={sim_passed}, rejections={rejections}"
            else:
                outcome = f"unexpected status {r.status_code}"

        print(f"  [{'PASS' if passed else 'FAIL'}] {t['name']}: {outcome}")
        safety_results.append({
            "name": t["name"],
            "request": t["req"],
            "expect": t["expect"],
            "passed": passed,
            "outcome": outcome,
        })
    results["safety_boundaries"] = safety_results

    # 6. SSE Replay Buffer & Duplicate Race Probe
    print("\n--- 6. SSE Late-Joiner Replay & Concurrency Race ---")
    # A. Late joiner on completed job
    tcs_resp = client.post("/api/analysis", json={"symbol": "TCS"})
    tcs_id = tcs_resp.json()["job_id"]
    for _ in range(60):
        st = client.get(f"/api/analysis/{tcs_id}").json()
        if st["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    ev_list = []
    with client.stream("GET", f"/api/analysis/{tcs_id}/stream") as stream:
        cur_event = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                cur_event = line.replace("event: ", "").strip()
            elif line.startswith("data: ") and cur_event:
                data = json.loads(line.replace("data: ", "").strip())
                ev_list.append({"event": cur_event, "data": data})
                cur_event = None

    event_names = [e["event"] for e in ev_list]
    has_started = "job_started" in event_names
    has_decision = "decision_card" in event_names
    has_completed = "job_completed" in event_names
    print(f"  Late-joiner received {len(ev_list)} events: started={has_started}, decision={has_decision}, completed={has_completed}")

    # B. Mid-flight race probe
    async def probe_mid_flight_race():
        job = AnalysisJob("probe_mid_flight", "RELIANCE", "2026-09-23", "equity")
        job.emit_event("event_1", {"index": 1})
        q = asyncio.Queue()
        sub = (q, asyncio.get_running_loop())
        job.subscribers.append(sub)
        job.emit_event("event_2", {"index": 2})
        await asyncio.sleep(0.001)

        delivered = []
        for e in list(job.events):
            delivered.append(e["event"])
        while not q.empty():
            delivered.append(q.get_nowait()["event"])
        return delivered

    delivered_events = asyncio.run(probe_mid_flight_race())
    duplicates = [ev for ev in set(delivered_events) if delivered_events.count(ev) > 1]
    has_race_dupes = len(duplicates) > 0
    print(f"  [{'FAIL' if has_race_dupes else 'PASS'}] Mid-flight subscription race duplicates: {duplicates}")

    results["sse_durability"] = {
        "late_joiner_event_count": len(ev_list),
        "late_joiner_complete": (has_started and has_decision and has_completed),
        "mid_flight_race_has_duplicates": has_race_dupes,
        "duplicated_events": duplicates,
    }

    # Save summary report to JSON
    with open("tests/adversarial/stress_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nAdversarial stress results written to tests/adversarial/stress_results.json")

if __name__ == "__main__":
    run_adversarial_suite()
