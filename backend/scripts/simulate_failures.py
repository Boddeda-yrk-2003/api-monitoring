#!/usr/bin/env python3
"""
Failure simulation runner (CLI).

Executes every scenario against a running APIGuard backend, verifies that the
monitoring pipeline detected it, and writes the evidence to disk:

    backend/data/failure-test-results.json
    backend/data/failure-test-results.csv

Usage
-----
    python scripts/simulate_failures.py                    # run all scenarios
    python scripts/simulate_failures.py --only auth,rate_limit
    python scripts/simulate_failures.py --auto-resolve     # clean up afterwards
    python scripts/simulate_failures.py --base http://localhost:8000
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_DEFAULT = "http://localhost:8000"
OUT_DIR = Path(__file__).resolve().parents[1] / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def bar(width: int = 78) -> str:
    return "─" * width


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the APIGuard failure scenarios end to end.")
    parser.add_argument("--base", default=BASE_DEFAULT)
    parser.add_argument("--only", default="", help="comma separated scenario ids")
    parser.add_argument("--auto-resolve", action="store_true", help="resolve the created incidents afterwards")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between scenarios")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    print(bar())
    print("  APIGuard · Failure simulation & detection test")
    print(f"  target: {base}    started: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    print(bar())

    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{base}/health")
        if health.status_code != 200:
            print(f"  ✗ backend not healthy at {base} (HTTP {health.status_code})")
            return 2
        print("  ✓ backend healthy\n")

        scenarios = client.get(f"{base}/monitor/scenarios").json()
        if args.only:
            wanted = {s.strip() for s in args.only.split(",")}
            scenarios = [s for s in scenarios if s["id"] in wanted]

        results = []
        for sc in scenarios:
            print(f"  ▸ {sc['id']:<15} {sc['title']}")
            started = time.time()
            try:
                res = client.post(f"{base}/monitor/simulate/{sc['id']}").json()
            except Exception as exc:  # noqa: BLE001
                print(f"      ✗ request failed: {exc}\n")
                results.append({"scenario": sc["id"], "detected": False, "error": str(exc)})
                continue
            wall = (time.time() - started) * 1000

            inc = res.get("incident") or {}
            alerts = res.get("alerts") or []
            detected = bool(res.get("detected"))
            mark = "✓" if detected else "✗"
            print(f"      {mark} HTTP {res.get('http_status') or 'no response'} in {res.get('latency_ms', 0):.0f} ms"
                  f"  → rule {inc.get('rule_id', '-')} [{inc.get('severity', '-')}]"
                  f"  · detected in {res.get('detection_latency_ms', 0):.0f} ms"
                  f"  · {len(alerts)} alert(s)")
            print(f"        incident : {inc.get('public_id', '-')}  ({inc.get('status', '-')})")
            print(f"        RCA      : {(inc.get('root_cause') or '-')[:110]}")
            channels = ", ".join("{}:{}".format(a["channel"], a["status"]) for a in alerts) or "-"
            print(f"        channels : {channels}")
            print(f"        wall     : {wall:.0f} ms\n")

            results.append(
                {
                    "scenario": sc["id"],
                    "title": res.get("title"),
                    "endpoint": res.get("endpoint"),
                    "http_status": res.get("http_status"),
                    "latency_ms": res.get("latency_ms"),
                    "expected_rule": sc.get("expected_rule"),
                    "rule_fired": inc.get("rule_id"),
                    "category": inc.get("category"),
                    "severity": inc.get("severity"),
                    "detected": detected,
                    "detection_latency_ms": res.get("detection_latency_ms"),
                    "incident_id": inc.get("public_id"),
                    "incident_db_id": inc.get("id"),
                    "root_cause": inc.get("root_cause"),
                    "recommended_actions": " | ".join(inc.get("recommended_actions") or []),
                    "alerts": ", ".join("{}:{}".format(a["channel"], a["status"]) for a in alerts),
                    "occurrences": inc.get("occurrences"),
                }
            )
            time.sleep(args.pause)

        # ------------------------------------------------------------ summary
        total = len(results)
        passed = sum(1 for r in results if r.get("detected"))
        print(bar())
        print(f"  RESULT: {passed}/{total} scenarios detected by the monitoring stack")
        print(bar())

        if args.auto_resolve:
            for r in results:
                if r.get("incident_db_id"):
                    try:
                        client.post(f"{base}/monitor/incidents/{r['incident_db_id']}/resolve")
                    except Exception:  # noqa: BLE001
                        pass
            print("  · created incidents resolved (--auto-resolve)\n")

    # ------------------------------------------------------------- artefacts
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    json_path = OUT_DIR / "failure-test-results.json"
    csv_path = OUT_DIR / "failure-test-results.csv"
    run_path = OUT_DIR / f"failure-test-run-{ts}.json"

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "target": base,
        "total": total,
        "detected": passed,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if results:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)

    print(f"  ✓ {json_path}")
    print(f"  ✓ {csv_path}")
    print(f"  ✓ {run_path} (timestamped copy)\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
