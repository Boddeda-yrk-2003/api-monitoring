import React from 'react'
import {
  Ban,
  CheckCircle2,
  Clock,
  Download,
  FlaskConical,
  Gauge,
  KeyRound,
  PlayCircle,
  Radio,
  RefreshCw,
  ServerCrash,
  ShieldAlert,
  Timer,
  Zap,
} from 'lucide-react'
import api from '../lib/api'
import { pushToast, useApi } from '../lib/hooks'
import RcaPanel from '../components/RcaPanel'
import { Badge, EmptyState, SectionHeader, StatusPill } from '../components/ui'
import { CHANNEL_LABEL, download, fmtMs, fmtNumber, toCsv } from '../lib/format'

const ICONS = {
  auth: KeyRound,
  timeout: Timer,
  server_error: ServerCrash,
  rate_limit: Ban,
  slow_response: Gauge,
  health_failure: ShieldAlert,
  downtime: Radio,
}

function ScenarioCard({ scenario, onRun, running, lastResult }) {
  const Icon = ICONS[scenario.id] ?? FlaskConical
  return (
    <div className="card card-hover flex animate-fadeUp flex-col">
      <div className="flex items-start justify-between gap-3">
        <span className="rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-transparent p-2 text-brand-300">
          <Icon size={17} />
        </span>
        {lastResult ? (
          <StatusPill status={lastResult.detected ? 'resolved' : 'warning'} label={lastResult.detected ? 'Detected' : 'No alert'} />
        ) : (
          <Badge>{scenario.expected_rule}</Badge>
        )}
      </div>

      <h3 className="mt-3 text-[13.5px] font-semibold text-white">{scenario.title}</h3>
      <p className="mt-1 flex-1 text-[11.5px] leading-relaxed text-slate-400">{scenario.description}</p>

      <p className="mt-3 rounded-lg border border-white/[0.06] bg-black/20 px-2.5 py-2 font-mono text-[10.5px] text-slate-500">
        GET {scenario.endpoint}
      </p>

      <div className="mt-3 space-y-1.5 text-[11px] text-slate-500">
        <p className="flex items-center gap-1.5">
          <Zap size={11} className="text-amber-300" /> expected: {scenario.title}
        </p>
        <p className="flex items-center gap-1.5">
          <ShieldAlert size={11} className="text-brand-300" /> rule: <span className="font-mono">{scenario.expected_rule}</span>
        </p>
        {lastResult && (
          <p className="flex items-center gap-1.5">
            <Clock size={11} className="text-emerald-300" /> detected in {fmtNumber(lastResult.detection_latency_ms)} ms ·
            HTTP {lastResult.http_status ?? 'timeout/err'}
          </p>
        )}
      </div>

      <button onClick={() => onRun(scenario.id)} disabled={running} className="btn-primary mt-4 w-full">
        {running ? <RefreshCw size={14} className="animate-spin" /> : <PlayCircle size={14} />}
        {running ? 'Running…' : 'Run scenario'}
      </button>
    </div>
  )
}

export default function FailureLab() {
  const scenarios = useApi(() => api.scenarios(), [], 0)
  const [running, setRunning] = React.useState(null)
  const [results, setResults] = React.useState({})
  const [active, setActive] = React.useState(null)

  const run = async (id) => {
    setRunning(id)
    try {
      const res = await api.simulate(id)
      setResults((prev) => ({ ...prev, [id]: res }))
      setActive(id)
      pushToast({
        tone: res.detected ? 'success' : 'error',
        title: `${res.title} — ${res.detected ? 'detected' : 'not detected'}`,
        message: res.message,
      })
    } catch (err) {
      pushToast({ tone: 'error', title: 'Scenario failed', message: err.message })
    } finally {
      setRunning(null)
    }
  }

  const runAll = async () => {
    for (const s of scenarios.data ?? []) {
      // eslint-disable-next-line no-await-in-loop
      await run(s.id)
    }
  }

  const all = Object.values(results)
  const exportJson = () => download('failure-lab-results.json', JSON.stringify(all, null, 2))
  const exportCsv = () =>
    download(
      'failure-lab-results.csv',
      toCsv(
        all.map((r) => ({
          scenario: r.scenario,
          title: r.title,
          endpoint: r.endpoint,
          http_status: r.http_status ?? 'n/a',
          latency_ms: r.latency_ms,
          expected_rule: r.incident?.rule_id ?? '',
          detected: r.detected,
          detection_latency_ms: r.detection_latency_ms,
          severity: r.incident?.severity ?? '',
          incident_id: r.incident?.public_id ?? '',
          root_cause: r.incident?.root_cause ?? '',
          alerts: r.alerts?.map((a) => `${a.channel}:${a.status}`).join(' | ') ?? '',
        })),
      ),
      'text/csv',
    )

  const current = active ? results[active] : null

  return (
    <div className="space-y-5">
      <div className="card animate-fadeUp">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-white">Failure simulation &amp; root cause analysis</h2>
            <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-slate-400">
              Each scenario calls the sample API the way a real client would, then feeds the observed result straight into
              the detection engine. The engine classifies the failure, runs the RCA engine, opens/updates an incident and
              dispatches notifications on every configured channel — all within milliseconds.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={runAll} disabled={!!running} className="btn-primary">
              <FlaskConical size={14} /> Run all scenarios
            </button>
            {all.length > 0 && (
              <>
                <button onClick={exportJson} className="btn-ghost"><Download size={14} /> JSON</button>
                <button onClick={exportCsv} className="btn-ghost"><Download size={14} /> CSV</button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------ scenarios */}
      <div>
        <SectionHeader title="Scenarios" subtitle="Click a scenario to trigger it and watch the detection pipeline" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {scenarios.loading && !scenarios.data
            ? [0, 1, 2, 3].map((i) => <div key={i} className="h-64 animate-shimmer rounded-2xl bg-white/[0.04]" />)
            : (scenarios.data ?? []).map((s) => (
                <ScenarioCard key={s.id} scenario={s} onRun={run} running={running === s.id} lastResult={results[s.id]} />
              ))}
        </div>
      </div>

      {/* --------------------------------------------------------- result */}
      {current && (
        <div className="card animate-fadeUp">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-white">
              Result · {current.title}
            </h2>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge>HTTP {current.http_status ?? 'no response'}</Badge>
              <Badge><Clock size={10} /> {fmtMs(current.latency_ms)}</Badge>
              <Badge><Zap size={10} /> detected in {fmtNumber(current.detection_latency_ms)} ms</Badge>
              {current.alerts?.map((a, i) => (
                <Badge key={i} className={a.status === 'sent' ? 'text-emerald-300' : a.status === 'failed' ? 'text-rose-300' : 'text-sky-300'}>
                  {CHANNEL_LABEL[a.channel]} · {a.status}
                </Badge>
              ))}
            </div>
          </div>

          {current.incident ? (
            <RcaPanel incident={current.incident} />
          ) : (
            <EmptyState icon={ShieldAlert} title="No incident raised" hint="The result did not match any alert rule." />
          )}

          {current.raw_response && (
            <details className="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3">
              <summary className="cursor-pointer text-[12px] font-medium text-slate-300">Raw API response</summary>
              <pre className="mt-2 overflow-auto rounded-lg bg-black/40 p-3 font-mono text-[11px] text-slate-300">
                {JSON.stringify(current.raw_response, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* --------------------------------------------------------- matrix */}
      {all.length > 0 && (
        <div className="card animate-fadeUp">
          <SectionHeader
            title="Test matrix"
            subtitle="One row per executed scenario — exportable as delivery evidence"
            right={<span className="text-[11px] text-slate-500">{all.length} executed</span>}
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead>
                <tr className="border-b border-white/[0.07]">
                  {['Scenario', 'Endpoint', 'HTTP', 'Latency', 'Rule fired', 'Detected', 'Detection time', 'Severity', 'Incident', 'Alerts'].map((h) => (
                    <th key={h} className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {all.map((r) => (
                  <tr key={r.scenario} className="border-b border-white/[0.04] last:border-0">
                    <td className="px-3 py-2 text-slate-200">{r.title}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-500">{r.endpoint}</td>
                    <td className={`px-3 py-2 font-mono ${(r.http_status ?? 0) >= 500 ? 'text-rose-300' : (r.http_status ?? 0) >= 400 ? 'text-amber-300' : 'text-emerald-300'}`}>
                      {r.http_status ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-400">{fmtMs(r.latency_ms)}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-300">{r.incident?.rule_id ?? '—'}</td>
                    <td className="px-3 py-2">
                      {r.detected ? <CheckCircle2 size={14} className="text-emerald-400" /> : <span className="text-[11px] text-slate-500">no</span>}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-400">{fmtNumber(r.detection_latency_ms)} ms</td>
                    <td className="px-3 py-2">
                      {r.incident?.severity ? <StatusPill status={r.incident.severity} /> : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10.5px] text-slate-500">{r.incident?.public_id ?? '—'}</td>
                    <td className="px-3 py-2 text-[11px] text-slate-400">
                      {r.alerts?.map((a) => `${CHANNEL_LABEL[a.channel]} (${a.status})`).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
