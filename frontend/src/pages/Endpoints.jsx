import React from 'react'
import { Activity, Clock, Radar, RefreshCw, Timer, TriangleAlert } from 'lucide-react'
import api from '../lib/api'
import { useApi } from '../lib/hooks'
import { LatencyChart } from '../components/charts'
import { Badge, EmptyState, KeyValue, SectionHeader, Skeleton, Sparkline, StatusPill, UptimeStrip } from '../components/ui'
import { fmtDateTime, fmtMs, fmtNumber, fmtPct, timeAgo } from '../lib/format'

function EndpointRow({ ep, active, onSelect }) {
  return (
    <button
      onClick={() => onSelect(ep.id)}
      className={`w-full rounded-xl border px-3 py-3 text-left transition ${
        active ? 'border-brand-500/40 bg-brand-500/[0.08]' : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-slate-100">{ep.name}</p>
          <p className="truncate font-mono text-[11px] text-slate-500">{ep.method} {ep.path}</p>
        </div>
        <StatusPill status={ep.status} />
      </div>
      <div className="mt-2.5 flex items-center gap-3">
        <div className="flex-1">
          <Sparkline data={ep.sparkline} height={26} stroke={ep.status === 'healthy' ? '#34D399' : ep.status === 'down' ? '#FB7185' : '#FBBF24'} />
        </div>
        <span className={`font-mono text-[11px] ${ep.uptime_pct >= 99 ? 'text-emerald-300' : ep.uptime_pct >= 95 ? 'text-amber-300' : 'text-rose-300'}`}>
          {fmtPct(ep.uptime_pct, 2)}
        </span>
      </div>
    </button>
  )
}

export default function Endpoints({ window }) {
  const endpoints = useApi(() => api.endpoints(window), [window], 20000)
  const [selected, setSelected] = React.useState(null)

  const list = endpoints.data ?? []
  const current = list.find((e) => e.id === selected) ?? list.find((e) => e.enabled) ?? null

  const uptime = useApi(() => (current ? api.uptime(current.id, 24) : Promise.resolve([])), [current?.id], 60000)
  const series = useApi(
    () => (current?.enabled ? api.timeseries(window, current.id) : Promise.resolve([])),
    [current?.id, window],
    30000,
  )
  const checks = useApi(() => (current ? api.checks(current.id, 40) : Promise.resolve([])), [current?.id], 30000)

  React.useEffect(() => {
    if (!selected && list.length) setSelected(list.find((e) => e.enabled)?.id ?? list[0].id)
  }, [list, selected])

  return (
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
      {/* ------------------------------------------------------------- list */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Monitored endpoints"
          subtitle={`${list.filter((e) => e.enabled).length} active · ${list.filter((e) => !e.enabled).length} chaos (not probed)`}
        />
        <div className="space-y-2">
          {endpoints.loading && !endpoints.data && <Skeleton className="h-20 w-full" />}
          {list.map((ep) => (
            <EndpointRow key={ep.id} ep={ep} active={current?.id === ep.id} onSelect={setSelected} />
          ))}
        </div>
        <p className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5 text-[11px] leading-relaxed text-slate-500">
          Chaos endpoints (<span className="font-mono">/simulate-*</span>) are excluded from the continuous probe loop on purpose — they
          are triggered on demand from the <span className="text-slate-300">Failure Lab</span>.
        </p>
      </div>

      {/* ----------------------------------------------------------- detail */}
      <div className="space-y-5">
        {current && (
          <>
            <div className="card animate-fadeUp">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-white">{current.name}</h2>
                    <StatusPill status={current.status} pulse={current.status === 'down'} />
                    {!current.enabled && <Badge>chaos endpoint</Badge>}
                  </div>
                  <p className="mt-1 font-mono text-[12px] text-slate-500">{current.method} {current.path}</p>
                  <p className="mt-1.5 max-w-2xl text-[12.5px] text-slate-400">{current.description}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge>criticality: {current.criticality}</Badge>
                  <Badge>expects HTTP {current.expected_status}</Badge>
                  <Badge>SLO {fmtMs(current.latency_threshold_ms)}</Badge>
                </div>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  { label: 'Uptime', value: fmtPct(current.uptime_pct, 2), icon: Activity },
                  { label: 'Avg latency', value: fmtMs(current.avg_latency_ms), icon: Timer },
                  { label: 'p95 / max', value: `${fmtMs(current.p95_latency_ms)} / ${fmtMs(current.max_latency_ms)}`, icon: Clock },
                  { label: 'Failed checks', value: `${fmtNumber(current.failed_checks)} / ${fmtNumber(current.total_checks)}`, icon: TriangleAlert },
                ].map((m) => (
                  <div key={m.label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                    <p className="flex items-center gap-1.5 label"><m.icon size={11} /> {m.label}</p>
                    <p className="mt-1.5 text-[15px] font-semibold text-white">{m.value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5">
                <div className="mb-2 flex items-center justify-between">
                  <p className="label">24h availability (30 min slots)</p>
                  <span className="text-[11px] text-slate-500">last check {timeAgo(current.last_checked_at)}</span>
                </div>
                <UptimeStrip slots={uptime.data ?? []} />
                <div className="mt-2 flex items-center gap-4 text-[10.5px] text-slate-500">
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-emerald-500/80" /> up</span>
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-amber-500/80" /> degraded</span>
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-rose-500/80" /> down</span>
                </div>
              </div>
            </div>

            <div className="card animate-fadeUp">
              <SectionHeader title="Latency history" subtitle={`Probe latency for ${current.path}`} />
              {series.loading && !series.data ? <Skeleton className="h-[240px] w-full" /> : <LatencyChart data={series.data ?? []} height={240} />}
            </div>

            <div className="card animate-fadeUp">
              <SectionHeader
                title="Recent probe results"
                subtitle="Raw synthetic check records"
                right={<span className="text-[11px] text-slate-500">{checks.data?.length ?? 0} rows</span>}
              />
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-left text-[12px]">
                  <thead className="sticky top-0 bg-ink-850/95 backdrop-blur">
                    <tr className="border-b border-white/[0.07]">
                      {['Time', 'Status', 'Latency', 'Result', 'Request id'].map((h) => (
                        <th key={h} className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(checks.data ?? []).map((c) => (
                      <tr key={c.id} className="border-b border-white/[0.04] last:border-0">
                        <td className="px-3 py-1.5 font-mono text-slate-400">{fmtDateTime(c.checked_at)}</td>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono ${c.status_code >= 500 ? 'text-rose-300' : c.status_code >= 400 ? 'text-amber-300' : 'text-emerald-300'}`}>
                            {c.status_code ?? '—'}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 font-mono text-slate-300">{fmtMs(c.latency_ms)}</td>
                        <td className="px-3 py-1.5">
                          {c.ok ? (
                            <span className="text-emerald-300">ok</span>
                          ) : (
                            <span className="text-rose-300">{c.error_type || 'failure'}</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-[10.5px] text-slate-600">{c.request_id || '—'}</td>
                      </tr>
                    ))}
                    {(checks.data ?? []).length === 0 && !checks.loading && (
                      <tr>
                        <td colSpan={5}>
                          <EmptyState icon={Radar} title="No probe data" hint="This endpoint is not part of the continuous probe loop." />
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
