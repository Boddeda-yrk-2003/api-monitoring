import React from 'react'
import {
  Activity,
  AlertOctagon,
  ArrowUpRight,
  BellRing,
  Clock,
  Gauge,
  Percent,
  ServerCrash,
  ShieldCheck,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import api from '../lib/api'
import { useApi } from '../lib/hooks'
import { LatencyChart, RequestsChart, StatusDonut, StatusLegend } from '../components/charts'
import { Badge, EmptyState, SectionHeader, Sparkline, StatCard, StatusPill, Skeleton } from '../components/ui'
import { CHANNEL_LABEL, fmtMs, fmtNumber, fmtPct, timeAgo } from '../lib/format'

function EndpointCard({ ep, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card card-hover w-full animate-fadeUp text-left"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-white">{ep.name}</p>
          <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">{ep.method} {ep.path}</p>
        </div>
        <StatusPill status={ep.status} pulse={ep.status === 'down'} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="label">Uptime</p>
          <p className={`mt-1 text-sm font-semibold ${ep.uptime_pct >= 99 ? 'text-emerald-300' : ep.uptime_pct >= 95 ? 'text-amber-300' : 'text-rose-300'}`}>
            {fmtPct(ep.uptime_pct, 2)}
          </p>
        </div>
        <div>
          <p className="label">p95</p>
          <p className="mt-1 text-sm font-semibold text-slate-200">{fmtMs(ep.p95_latency_ms)}</p>
        </div>
        <div>
          <p className="label">Errors</p>
          <p className="mt-1 text-sm font-semibold text-slate-200">{fmtPct(ep.error_rate_pct, 1)}</p>
        </div>
      </div>

      <div className="mt-4">
        <Sparkline data={ep.sparkline} stroke={ep.status === 'healthy' ? '#34D399' : ep.status === 'down' ? '#FB7185' : '#FBBF24'} height={38} />
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3 text-[11px] text-slate-500">
        <span>{fmtNumber(ep.total_checks)} checks</span>
        <span className="flex items-center gap-1">
          {ep.open_incidents > 0 ? (
            <span className="text-rose-300">{ep.open_incidents} open</span>
          ) : (
            <span className="text-emerald-300/80">no open incidents</span>
          )}
          <ArrowUpRight size={12} />
        </span>
      </div>
    </button>
  )
}

export default function Overview({ window, onNavigate }) {
  const summary = useApi(() => api.summary(window), [window], 15000)
  const series = useApi(() => api.timeseries(window), [window], 20000)
  const endpoints = useApi(() => api.endpoints(window), [window], 20000)
  const traffic = useApi(() => api.traffic(window), [window], 30000)
  const incidents = useApi(() => api.incidents({ limit: 6 }), [], 20000)
  const alerts = useApi(() => api.alerts({ limit: 8 }), [], 20000)

  const s = summary.data
  const loading = summary.loading && !s

  const kpis = [
    {
      label: 'API uptime',
      value: fmtPct(s?.uptime_pct, 2),
      sub: `${fmtNumber(s?.total_checks)} synthetic checks · ${window}`,
      icon: ShieldCheck,
      tone: (s?.uptime_pct ?? 100) >= 99.5 ? 'emerald' : (s?.uptime_pct ?? 100) >= 98 ? 'amber' : 'rose',
    },
    {
      label: 'Avg response time',
      value: fmtMs(s?.avg_latency_ms),
      sub: `p95 ${fmtMs(s?.p95_latency_ms)} · max ${fmtMs(s?.max_latency_ms)}`,
      icon: Gauge,
      tone: 'cyan',
    },
    {
      label: 'Total API requests',
      value: fmtNumber(s?.total_requests),
      sub: `real inbound traffic · ${window}`,
      icon: Activity,
      tone: 'brand',
    },
    {
      label: 'Failed requests',
      value: fmtNumber(s?.failed_requests),
      sub: `${fmtPct(s?.error_rate_pct)} of all traffic`,
      icon: XCircle,
      tone: (s?.error_rate_pct ?? 0) > 5 ? 'rose' : 'violet',
    },
    {
      label: 'Error rate',
      value: fmtPct(s?.error_rate_pct),
      sub: `threshold ${fmtPct(5, 0)} · synthetic ${fmtPct(s?.check_error_rate_pct)}`,
      icon: Percent,
      tone: (s?.error_rate_pct ?? 0) > 5 ? 'rose' : 'emerald',
    },
    {
      label: 'Open incidents',
      value: fmtNumber(s?.open_incidents),
      sub: `${s?.critical_incidents ?? 0} critical · ${s?.alerts_last_24h ?? 0} alerts / 24h`,
      icon: AlertOctagon,
      tone: (s?.critical_incidents ?? 0) > 0 ? 'rose' : (s?.open_incidents ?? 0) > 0 ? 'amber' : 'emerald',
    },
  ]

  return (
    <div className="space-y-5">
      {/* ---------------------------------------------------------- KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} loading={loading} />
        ))}
      </div>

      {/* --------------------------------------------------------- charts 1 */}
      <div className="grid gap-5 xl:grid-cols-3">
        <div className="card animate-fadeUp xl:col-span-2">
          <SectionHeader
            title="Response time & failure trend"
            subtitle="Average, p95 and max probe latency with failed checks overlaid"
            right={
              <div className="flex items-center gap-2">
                <Badge><span className="h-1.5 w-1.5 rounded-full bg-cyan-400" /> avg</Badge>
                <Badge><span className="h-1.5 w-1.5 rounded-full bg-violet-400" /> p95</Badge>
                <Badge><span className="h-1.5 w-1.5 rounded-full bg-rose-400" /> failed</Badge>
              </div>
            }
          />
          {series.loading && !series.data ? (
            <Skeleton className="h-[260px] w-full" />
          ) : (
            <LatencyChart data={series.data ?? []} />
          )}
        </div>

        <div className="card animate-fadeUp">
          <SectionHeader title="HTTP status distribution" subtitle="Real inbound traffic by status code" />
          {traffic.loading && !traffic.data ? (
            <Skeleton className="h-[220px] w-full" />
          ) : (
            <>
              <StatusDonut data={traffic.data?.by_status ?? []} />
              <StatusLegend data={traffic.data?.by_status ?? []} />
            </>
          )}
        </div>
      </div>

      {/* --------------------------------------------------------- charts 2 */}
      <div className="grid gap-5 xl:grid-cols-3">
        <div className="card animate-fadeUp xl:col-span-2">
          <SectionHeader title="Synthetic check volume" subtitle="Successful vs failed probes per time bucket" />
          {series.loading && !series.data ? (
            <Skeleton className="h-[220px] w-full" />
          ) : (
            <RequestsChart data={series.data ?? []} />
          )}
        </div>

        <div className="card animate-fadeUp">
          <SectionHeader
            title="Alert feed"
            subtitle="Latest notifications"
            right={
              <button onClick={() => onNavigate('alerts')} className="text-[11px] text-brand-300 hover:text-brand-200">
                View all →
              </button>
            }
          />
          <ul className="space-y-2">
            {(alerts.data ?? []).slice(0, 6).map((a) => (
              <li key={a.id} className="flex items-start gap-2.5 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
                <span className="mt-0.5">
                  <BellRing size={13} className={a.status === 'sent' ? 'text-emerald-300' : a.status === 'failed' ? 'text-rose-300' : 'text-sky-300'} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium text-slate-200">{a.subject || a.incident_title}</p>
                  <p className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-slate-500">
                    <span className="uppercase tracking-wide">{CHANNEL_LABEL[a.channel] ?? a.channel}</span>
                    <span>·</span>
                    <span className={a.status === 'sent' ? 'text-emerald-300/80' : ''}>{a.status}</span>
                    <span>·</span>
                    <span>{timeAgo(a.created_at)}</span>
                  </p>
                </div>
              </li>
            ))}
            {(alerts.data ?? []).length === 0 && !alerts.loading && (
              <EmptyState icon={BellRing} title="No alerts yet" hint="Trigger a scenario in the Failure Lab to see alerts appear here." />
            )}
          </ul>
        </div>
      </div>

      {/* ------------------------------------------------------ endpoints */}
      <div>
        <SectionHeader
          title="Endpoint health"
          subtitle={`${endpoints.data?.filter((e) => e.enabled).length ?? 0} endpoints under active monitoring`}
          right={
            <button onClick={() => onNavigate('endpoints')} className="text-[11px] text-brand-300 hover:text-brand-200">
              Open endpoint detail →
            </button>
          }
        />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {(endpoints.data ?? []).filter((e) => e.enabled).map((ep) => (
            <EndpointCard key={ep.id} ep={ep} onClick={() => onNavigate('endpoints')} />
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------ incidents */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Recent incidents"
          subtitle="Every incident carries a root cause analysis and remediation plan"
          right={
            <button onClick={() => onNavigate('incidents')} className="text-[11px] text-brand-300 hover:text-brand-200">
              Incident console →
            </button>
          }
        />
        <ul className="divide-y divide-white/[0.05]">
          {(incidents.data ?? []).slice(0, 5).map((inc) => (
            <li key={inc.id} className="flex flex-wrap items-center gap-3 py-3">
              <StatusPill status={inc.severity} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-slate-200">{inc.title}</p>
                <p className="mt-0.5 truncate text-[11px] text-slate-500">{inc.root_cause}</p>
              </div>
              <Badge>{inc.rule_id}</Badge>
              <Badge><Clock size={10} /> {timeAgo(inc.detected_at)}</Badge>
              <StatusPill status={inc.status} />
            </li>
          ))}
          {(incidents.data ?? []).length === 0 && !incidents.loading && (
            <EmptyState icon={ShieldCheck} title="No incidents recorded" hint="The service is healthy. Use the Failure Lab to validate detection." />
          )}
        </ul>
      </div>
    </div>
  )
}
