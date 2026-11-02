# APIGuard — Frontend (React monitoring dashboard)

Dark-themed monitoring dashboard built with **React 18 + Vite 5 + Tailwind CSS 3
+ Recharts**. Full guide: [`../docs/05-frontend-guide.md`](../docs/05-frontend-guide.md).

## Run

```bash
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/monitor`, `/health`, `/users`, `/products`,
`/secure-data`, `/metrics` and `/docs` to `http://127.0.0.1:8000`
(see `vite.config.js`), so the browser only ever calls one origin.

```bash
npm run build        # production bundle → dist/
npm run preview      # serve the bundle on :4173
```

## Views

| Route | View |
|---|---|
| `#overview` | KPI cards, latency/failure trend, check volume, status donut, endpoint cards, incident + alert feed |
| `#endpoints` | per-endpoint SLOs, 24 h availability strip, latency history, raw probe records |
| `#incidents` | filters, incident detail, RCA panel (root cause, probable causes, evidence, stack trace, remediation), acknowledge / resolve / export |
| `#alerts` | channel cards (live vs dry-run), test buttons, alert history with provider payloads, captured exceptions |
| `#lab` | 7 failure scenarios, run one or all, live result + RCA + alert badges, JSON/CSV export |
| `#explorer` | call the sample API with an optional `X-API-Key` |
| `#settings` | engine/storage/integration summary, thresholds, channel credentials, active rule catalogue |

## Structure

```
src/
├── main.jsx / App.jsx      root + shell (hash routing, window state, toasts)
├── index.css               Tailwind layers + .card/.btn/.chip component classes
├── lib/
│   ├── api.js              REST client (mirrors /monitor/*)
│   ├── hooks.js            useApi (polling) · useInterval · toasts
│   └── format.js           fmtMs / fmtPct / fmtNumber / timeAgo / status styles
├── components/
│   ├── Layout.jsx          sidebar, mobile nav, top bar, probe button, toasts
│   ├── ui.jsx              StatusPill, StatCard, Sparkline, UptimeStrip, Table…
│   ├── charts.jsx          LatencyChart, RequestsChart, StatusDonut, StatusLegend
│   └── RcaPanel.jsx        root-cause presentation
└── pages/                  Overview · Endpoints · Incidents · Alerts · FailureLab · Explorer · Settings
```

## Notes

- Backend timestamps are naive UTC — `parseUtc()` re-attaches `Z` before parsing.
- Polling intervals: 15 s (summary), 20 s (charts/incidents), 30 s (traffic,
  alerts). Change them in the corresponding `useApi(..., intervalMs)` call.
- To point at a remote API: `VITE_API_BASE=https://api.example.com npm run dev`.
