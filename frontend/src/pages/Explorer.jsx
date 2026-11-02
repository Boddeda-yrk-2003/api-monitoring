import React from 'react'
import { KeyRound, Send, TerminalSquare } from 'lucide-react'
import api from '../lib/api'
import { pushToast } from '../lib/hooks'
import { Badge, KeyValue, SectionHeader, StatusPill } from '../components/ui'
import { fmtMs } from '../lib/format'

const PRESETS = [
  { path: '/health', label: 'GET /health', note: 'Liveness probe' },
  { path: '/users?limit=5', label: 'GET /users?limit=5', note: 'Sample users' },
  { path: '/products?limit=5', label: 'GET /products?limit=5', note: 'Sample products' },
  { path: '/users/999', label: 'GET /users/999', note: '404 scenario' },
  { path: '/secure-data', label: 'GET /secure-data', note: 'Requires X-API-Key' },
  { path: '/simulate-error', label: 'GET /simulate-error', note: 'HTTP 500' },
  { path: '/simulate-auth-error', label: 'GET /simulate-auth-error', note: 'HTTP 401' },
  { path: '/simulate-rate-limit', label: 'GET /simulate-rate-limit', note: 'HTTP 429 after quota' },
  { path: '/simulate-timeout?seconds=3.5', label: 'GET /simulate-timeout?seconds=3.5', note: 'Slow > 3s SLO' },
]

export default function Explorer() {
  const [path, setPath] = React.useState('/users?limit=5')
  const [apiKey, setApiKey] = React.useState('demo-api-key-123')
  const [busy, setBusy] = React.useState(false)
  const [result, setResult] = React.useState(null)

  const send = async () => {
    setBusy(true)
    const started = performance.now()
    try {
      const data = await api.callSample(path, apiKey || undefined)
      setResult({ ok: true, status: 200, data, ms: performance.now() - started })
    } catch (err) {
      const match = /^(\d{3})/.exec(err.message || '')
      setResult({ ok: false, status: match ? Number(match[1]) : 0, data: { error: err.message }, ms: performance.now() - started })
    } finally {
      setBusy(false)
      pushToast({ tone: 'info', title: 'Request recorded', message: `${path} was logged in request_logs and evaluated by the monitor.` })
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
      <div className="card animate-fadeUp">
        <SectionHeader title="Sample API explorer" subtitle="Requests are proxied to the FastAPI service" />

        <label className="label">Request</label>
        <div className="mt-1.5 flex gap-2">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-[12px] text-slate-200 outline-none focus:border-brand-500/60"
            placeholder="/users?limit=5"
          />
        </div>

        <label className="label mt-3 flex items-center gap-1.5"><KeyRound size={11} /> X-API-Key (optional)</label>
        <input
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-[12px] text-slate-200 outline-none focus:border-brand-500/60"
          placeholder="demo-api-key-123"
        />

        <button onClick={send} disabled={busy} className="btn-primary mt-4 w-full">
          <Send size={14} /> {busy ? 'Sending…' : 'Send request'}
        </button>

        <div className="divider" />
        <p className="label mb-2">Presets</p>
        <div className="space-y-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.path}
              onClick={() => setPath(p.path)}
              className={`flex w-full items-center justify-between rounded-lg border px-2.5 py-2 text-left transition ${
                path === p.path ? 'border-brand-500/40 bg-brand-500/[0.08]' : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05]'
              }`}
            >
              <span className="font-mono text-[11px] text-slate-300">{p.label}</span>
              <span className="text-[10px] text-slate-500">{p.note}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-5">
        <div className="card animate-fadeUp">
          <SectionHeader title="Response" subtitle={result ? `${path} · ${fmtMs(result.ms)}` : 'No request sent yet'} />
          {result ? (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <StatusPill status={result.status >= 500 ? 'down' : result.status >= 400 ? 'warning' : 'healthy'} label={`HTTP ${result.status}`} />
                <Badge>{fmtMs(result.ms)}</Badge>
                <Badge>logged in request_logs</Badge>
                {result.status >= 400 && <Badge className="text-amber-300">evaluated by live-traffic rule</Badge>}
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-xl border border-white/[0.07] bg-black/40 p-4 font-mono text-[11.5px] leading-relaxed text-emerald-200/90">
                {JSON.stringify(result.data, null, 2)}
              </pre>
            </>
          ) : (
            <div className="flex h-52 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 text-center">
              <TerminalSquare size={18} className="text-slate-600" />
              <p className="text-[12.5px] text-slate-400">Send a request to inspect the response</p>
              <p className="max-w-sm text-[11px] text-slate-500">
                Every call is captured with its status, latency and correlation id, and feeds the monitoring pipeline.
              </p>
            </div>
          )}
        </div>

        <div className="card animate-fadeUp">
          <SectionHeader title="Correlation & headers" subtitle="Useful when tracing a failure back to a request" />
          <div className="grid gap-x-8 md:grid-cols-2">
            <KeyValue label="X-Request-ID" value="echoed on every response" mono />
            <KeyValue label="X-Response-Time" value="server-side duration" mono />
            <KeyValue label="Swagger UI" value="/docs" mono />
            <KeyValue label="Prometheus metrics" value="/metrics" mono />
          </div>
        </div>
      </div>
    </div>
  )
}
