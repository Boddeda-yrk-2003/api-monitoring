# Frontend Guide — React monitoring dashboard

## 1. Requirements

| Requirement | Version |
|---|---|
| Node.js | 18+ (developed on 20 LTS) |
| npm | 9+ |
| Backend | running on `http://localhost:8000` |

## 2. Setup

```bash
cd api-monitoring/frontend

npm install          # ~170 packages
npm run dev          # http://localhost:5173
```

Production build:

```bash
npm run build        # → dist/
npm run preview      # serve the build on :4173
```

### How the browser reaches the API
`vite.config.js` proxies every backend path to `http://127.0.0.1:8000`, so the
app always talks to a **single origin**. For a different backend host set:

```bash
VITE_API_BASE=https://api.mycompany.com npm run dev
```

(`src/lib/api.js` prefixes every request with `import.meta.env.VITE_API_BASE`.)

## 3. Project layout

```
frontend/
├── index.html
├── vite.config.js          dev server + backend proxy
├── tailwind.config.js      theme (colours, animations, shadows)
├── postcss.config.js
└── src/
    ├── main.jsx            React root
    ├── App.jsx             shell: routing, window state, refresh, toasts
    ├── index.css           Tailwind layers + component classes (.card, .btn, .chip…)
    ├── lib/
    │   ├── api.js          REST client (one method per endpoint)
    │   ├── hooks.js        useApi (polling) · useInterval · toasts
    │   └── format.js       number/date/duration formatters, status styles
    ├── components/
    │   ├── Layout.jsx      sidebar, mobile nav, top bar, probe button, toasts
    │   ├── ui.jsx          StatusPill, StatCard, Sparkline, UptimeStrip, Table…
    │   ├── charts.jsx      LatencyChart, RequestsChart, StatusDonut, StatusLegend
    │   └── RcaPanel.jsx    root-cause presentation block
    └── pages/
        Overview.jsx  Endpoints.jsx  Incidents.jsx
        Alerts.jsx    FailureLab.jsx Explorer.jsx  Settings.jsx
```

## 4. Views

| View | Route | What it shows |
|---|---|---|
| **Overview** | `#overview` | 6 KPI cards, latency + failure trend, check volume, status donut, endpoint health grid, recent incidents, alert feed |
| **Endpoints** | `#endpoints` | endpoint list → detail: uptime %, avg/p95/max, 24 h availability strip, latency history, raw probe table |
| **Incidents** | `#incidents` | filters (status/severity) → incident → RCA panel (root cause, probable causes, evidence, stack trace, remediation, owner) + acknowledge / resolve / export |
| **Alerts** | `#alerts` | channel cards with live/dry-run state, test buttons, alert history with exact provider payloads, captured exceptions with tracebacks |
| **Failure Lab** | `#lab` | 7 scenarios → run individually or all → live result, RCA, alert badges, exportable test matrix (JSON/CSV) |
| **API Explorer** | `#explorer` | call any sample endpoint with an optional `X-API-Key` and inspect the response |
| **Settings** | `#settings` | engine/storage/integration summary, threshold editor, channel credentials, active rule catalogue |

Global controls: time-window chips (**15m · 1h · 6h · 24h · 7d**), refresh, and
**Run probe now** which forces a monitoring cycle.

## 5. Design system

| Token | Value | Usage |
|---|---|---|
| `ink-900` | `#070B16` | page canvas |
| `ink-850 / 800 / 700` | `#0A0F1E …` | surfaces, modals |
| `brand-400/500/600` | `#818CF8 / #6366F1 / #4F46E5` | primary actions, active nav |
| emerald / amber / rose | `#34D399 / #FBBF24 / #FB7185` | healthy / warning / critical |
| `shadow-card` | layered soft shadow | cards |
| `shadow-glow` | indigo glow | hover state |
| animations | `fadeUp`, `pulseRing`, `shimmer` | entrance, live dots, skeletons |

Custom classes live in `src/index.css`: `.card`, `.card-hover`, `.btn`,
`.btn-primary`, `.btn-ghost`, `.chip`, `.label`, `.mono`, `.divider`.

**Conventions**
- Every numeric value goes through `src/lib/format.js` (`fmtMs`, `fmtPct`,
  `fmtNumber`, `fmtDuration`, `timeAgo`).
- Backend timestamps are naive UTC — `parseUtc()` re-attaches `Z` before parsing.
- Status colours come from `STATUS_STYLES` keyed by status/severity so the
  palette never drifts between components.

## 6. Data fetching

```jsx
const summary = useApi(() => api.summary(window), [window], 15_000)
// → { data, error, loading, refresh }
```

- `intervalMs = 0` disables polling (one-shot fetch).
- Dependencies behave like `useEffect` deps; changing the window refetches.
- The shell bumps a `nonce` on refresh, remounting the active page so every
  widget refetches at once.
- `pushToast({ tone, title, message })` shows transient confirmations.

## 7. Accessibility & responsiveness
- Sidebar collapses into a horizontal scrollable nav below `1024px`.
- Charts use `ResponsiveContainer`; tables scroll horizontally on small screens.
- All interactive controls are real `<button>`/`<input>` elements with visible
  focus rings; colour is never the only signal (text labels accompany dots).

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Blank page / `net::ERR_CONNECTION_REFUSED` on `/monitor/*` | backend not running, or `vite.config.js` proxy target wrong |
| HMR websocket errors in the console | harmless when opening the dev server through a tunnel; the app still works |
| Charts render empty | no data in the selected window — run **Run probe now** or widen the window |
| `401` from the explorer on `/secure-data` | add header `X-API-Key: demo-api-key-123` |
| Styles look unstyled | run `npm install` (Tailwind/PostCSS missing) and restart Vite |
