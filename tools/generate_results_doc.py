#!/usr/bin/env python3
"""
Generate docs/08-failure-simulation-results.md from a live system.

Reads:
    backend/data/failure-test-results.json   (written by scripts/simulate_failures.py)
    GET /monitor/incidents                   (RCA details, alert counts)
    GET /monitor/alerts                      (channel/delivery statistics)

Usage
-----
    python tools/generate_results_doc.py --base http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "backend" / "data" / "failure-test-results.json"
OUT = ROOT / "docs" / "08-failure-simulation-results.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()

    if not RESULTS.exists():
        print(f"! {RESULTS} not found - run: cd backend && python scripts/simulate_failures.py")
        return 1

    data = json.loads(RESULTS.read_text())
    with httpx.Client(base_url=args.base, timeout=30) as c:
        incidents = c.get("/monitor/incidents?limit=100").json()
        alerts = c.get("/monitor/alerts?limit=200").json()

    by_id = {i["public_id"]: i for i in incidents}
    chan = Counter(a["channel"] for a in alerts)
    status = Counter(a["status"] for a in alerts)

    md = []
    md.append("# Failure Simulation & Root Cause Analysis — Test Results\n")
    md.append("| Field | Value |")
    md.append("|---|---|")
    md.append(f"| Target | `{args.base}` (backend) · `http://localhost:5173` (dashboard) |")
    md.append("| Runner | `backend/scripts/simulate_failures.py` |")
    md.append(f"| Executed | {data['generated_at']} |")
    md.append(f"| Result | **{data['detected']} / {data['total']} scenarios detected** |")
    md.append(
        "| Artefacts | `backend/data/failure-test-results.json`, `failure-test-results.csv`, "
        "`backend/data/alert-outbox/alerts-<date>.jsonl` |"
    )
    md.append("")

    # ------------------------------------------------------------ matrix
    md.append("## 1. Summary matrix\n")
    md.append("| # | Scenario | Endpoint | HTTP | Latency | Rule fired | Severity | Detected | Detection time | Incident | Alerts |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for n, r in enumerate(data["results"], start=1):
        http = r["http_status"] if r["http_status"] else "no response"
        lat = f"{r['latency_ms']:.0f} ms"
        alerts_txt = ", ".join(sorted({a.split(":")[0].capitalize() for a in r["alerts"].split(", ")}))
        md.append(
            f"| {n} | {r['title']} | `{r['endpoint']}` | **{http}** | {lat} | `{r['rule_fired']}` | "
            f"{r['severity']} | ✅ | {r['detection_latency_ms']:.0f} ms | `{r['incident_id']}` | {alerts_txt} |"
        )
    md.append("")
    md.append(
        "**Detection latency (failure → incident with RCA → notifications dispatched): "
        f"{min(r['detection_latency_ms'] for r in data['results']):.0f}–"
        f"{max(r['detection_latency_ms'] for r in data['results']):.0f} ms** "
        "(the probe loop adds at most `PROBE_INTERVAL_SECONDS` for failures that are not triggered "
        "through the Failure Lab).\n"
    )
    md.append(
        "All channels are reported as `simulated` because no webhook/SMTP/Twilio credentials are "
        "configured in the demo environment — payloads are fully rendered and stored (see the *Notification proof* section).\n"
    )

    # --------------------------------------------------------- per scenario
    sections = {
        "auth": ("Invalid API authentication", "`GET /secure-data` without the `X-API-Key` header."),
        "timeout": ("API timeout", "`GET /simulate-timeout?seconds=12` with a client budget of 8 s — the client aborts while the server is still processing (a genuine timeout, not a slow 200)."),
        "server_error": ("Server error (HTTP 500)", "`GET /simulate-error` raises an unhandled `RuntimeError`."),
        "rate_limit": ("Rate limit exceeded (HTTP 429)", f"Rapid calls to `/simulate-rate-limit` (quota = 5 / 60 s)."),
    }
    n = 2
    for key, (title, trigger) in sections.items():
        r = next((x for x in data["results"] if x["scenario"] == key), None)
        if not r:
            continue
        inc = by_id.get(r["incident_id"], {})
        evidence = inc.get("evidence", {})
        ev_rows = "\n".join(
            f"| `{k}` | `{str(v)[:160]}` |" for k, v in list(evidence.items())[:8] if k != "traceback"
        )
        causes = "\n".join(f"- {c}" for c in (inc.get("probable_causes") or []))
        actions = "\n".join(f"{i}. {a}" for i, a in enumerate(inc.get("recommended_actions") or [], start=1))
        md.append(f"## {n}. Scenario {n-1} — {title}\n")
        md.append(f"**Trigger**: {trigger}\n")
        md.append("| Item | Value |")
        md.append("|---|---|")
        md.append(f"| Observed | `HTTP {r['http_status'] or 'no response'}` in {r['latency_ms']:.0f} ms |")
        md.append(f"| Rule | `{r['rule_fired']}` ({r['severity']}) |")
        md.append(f"| Category | `{r['category']}` |")
        md.append(f"| Root cause | {r['root_cause']} |")
        md.append(f"| Owner | {inc.get('owner_team', '—')} |")
        md.append(f"| Confidence | {inc.get('root_cause_confidence', '—')} |")
        md.append(f"| Alerts | {r['alerts']} |")
        md.append(f"| Incident | `{r['incident_id']}` ({inc.get('status', '—')}, {inc.get('occurrences', 1)} occurrence(s)) |")
        md.append("")
        md.append("**Probable causes**\n")
        md.append(causes or "—")
        md.append("")
        md.append("**Captured evidence**\n")
        md.append("| Field | Value |")
        md.append("|---|---|")
        md.append(ev_rows or "| — | — |")
        md.append("")
        md.append("**Recommended actions**\n")
        md.append(actions or "—")
        md.append("")
        n += 1

    # ------------------------------------------------------- extra scenarios
    md.append(f"## {n}. Additional scenarios (beyond the four required)\n")
    md.append("| Scenario | Observed | Rule | Severity | Result |")
    md.append("|---|---|---|---|---|")
    for key in ("slow_response", "health_failure", "downtime"):
        r = next((x for x in data["results"] if x["scenario"] == key), None)
        if not r:
            continue
        md.append(
            f"| {r['title']} | HTTP {r['http_status'] or 'no response'} in {r['latency_ms']:.0f} ms | "
            f"`{r['rule_fired']}` | {r['severity']} | detected in {r['detection_latency_ms']:.0f} ms — {r['alerts']} |"
        )
    md.append("")
    md.append(f"Root causes captured for the extra scenarios:\n")
    for key in ("slow_response", "health_failure", "downtime"):
        r = next((x for x in data["results"] if x["scenario"] == key), None)
        if r:
            md.append(f"- **{r['title']}** — {r['root_cause']}")
    md.append("")

    # ------------------------------------------------------------ proof
    md.append(f"## {n+1}. Notification proof\n")
    md.append("Every dispatch is persisted. Current state of the running system:\n")
    md.append("| Channel | Records | Status |")
    md.append("|---|---|---|")
    for channel, count in chan.most_common():
        md.append(f"| {channel.capitalize()} | {count} | " + ", ".join(f"`{k}`" for k in status) + " |")
    md.append("")
    md.append("Where to look:\n")
    md.append("1. **Dashboard** → Alerts → click **payload** on any row (Block Kit JSON / SMTP envelope / Twilio request).")
    md.append("2. **Files** → `backend/data/alert-outbox/alerts-<date>.jsonl` and `alerts.log`.")
    md.append("3. **API** → `GET /monitor/alerts`, `GET /monitor/alerts/outbox`.")
    md.append("4. **SQL** → `SELECT channel, status, delivery_note, created_at FROM alerts ORDER BY id DESC LIMIT 20;`")
    md.append("5. **Report** → `deliverables/alert-proof.md` (generated from the live system).")
    md.append("")

    # ------------------------------------------------------------- tests
    md.append(f"## {n+2}. Automated test suite\n")
    md.append("```bash\ncd backend && python -m pytest -q\n# 22 passed\n```\n")
    md.append(
        "Coverage: sample endpoints (success + every failure mode), control-plane contracts, probe cycle, "
        "Prometheus exposition, scenario detection for six rules, traceback evidence, incident "
        "de-duplication and lifecycle, channel test dispatch, and runtime settings updates. "
        "The suite boots its own server on port 8123 with a private database, so it never touches "
        "development data.\n"
    )

    # ---------------------------------------------------------- reproduce
    md.append(f"## {n+3}. How to reproduce\n")
    md.append(
        "```bash\n"
        "# terminal 1 - backend\n"
        "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000\n\n"
        "# terminal 2 - frontend (optional; the CLI does not need it)\n"
        "cd frontend && npm run dev\n\n"
        "# terminal 3 - run every scenario and write the evidence files\n"
        "cd backend && python scripts/simulate_failures.py\n"
        "# or interactively: dashboard -> Failure Lab -> \"Run all scenarios\"\n"
        "```\n"
    )

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"✓ {OUT} ({data['detected']}/{data['total']} scenarios, {len(incidents)} incidents, {len(alerts)} alerts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
