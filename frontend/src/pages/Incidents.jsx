import React from 'react'
import { AlertTriangle, CheckCircle2, Download, Filter, ShieldCheck } from 'lucide-react'
import api from '../lib/api'
import { pushToast, useApi } from '../lib/hooks'
import RcaPanel from '../components/RcaPanel'
import { Badge, EmptyState, SectionHeader, StatusPill, Skeleton } from '../components/ui'
import { download, fmtDuration, timeAgo } from '../lib/format'

const STATUS_FILTERS = ['all', 'open', 'acknowledged', 'resolved']
const SEVERITY_FILTERS = ['all', 'critical', 'warning', 'info']

export default function Incidents() {
  const [status, setStatus] = React.useState('all')
  const [severity, setSeverity] = React.useState('all')
  const [selectedId, setSelectedId] = React.useState(null)

  const incidents = useApi(() => api.incidents({ status, severity, limit: 100 }), [status, severity], 15000)
  const list = incidents.data ?? []
  const selected = list.find((i) => i.id === selectedId) ?? list[0] ?? null

  const act = async (fn, message) => {
    try {
      await fn()
      pushToast({ tone: 'success', title: message })
      incidents.refresh()
    } catch (err) {
      pushToast({ tone: 'error', title: 'Action failed', message: err.message })
    }
  }

  const exportIncident = () => {
    if (!selected) return
    download(`incident-${selected.public_id}.json`, JSON.stringify(selected, null, 2))
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
      {/* ------------------------------------------------------------ list */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Incident console"
          subtitle="Detection → classification → root cause → remediation"
        />

        <div className="mb-3 space-y-2">
          <div className="flex items-center gap-1.5">
            <Filter size={12} className="text-slate-500" />
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`rounded-lg px-2 py-1 text-[11px] font-medium capitalize transition ${
                  status === s ? 'bg-brand-500/20 text-white ring-1 ring-brand-500/40' : 'text-slate-400 hover:bg-white/[0.05]'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3" />
            {SEVERITY_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setSeverity(s)}
                className={`rounded-lg px-2 py-1 text-[11px] font-medium capitalize transition ${
                  severity === s ? 'bg-white/10 text-white ring-1 ring-white/20' : 'text-slate-400 hover:bg-white/[0.05]'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="max-h-[70vh] space-y-2 overflow-auto pr-1">
          {incidents.loading && !incidents.data && <Skeleton className="h-24 w-full" />}
          {list.map((inc) => (
            <button
              key={inc.id}
              onClick={() => setSelectedId(inc.id)}
              className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                selected?.id === inc.id
                  ? 'border-brand-500/40 bg-brand-500/[0.08]'
                  : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <StatusPill status={inc.severity} />
                  <Badge>{inc.rule_id}</Badge>
                </div>
                <span className="text-[10.5px] text-slate-500">{timeAgo(inc.detected_at)}</span>
              </div>
              <p className="mt-2 truncate text-[12.5px] font-medium text-slate-100">{inc.title}</p>
              <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-500">{inc.root_cause}</p>
              <div className="mt-2 flex items-center justify-between">
                <span className="font-mono text-[10.5px] text-slate-600">{inc.public_id}</span>
                <StatusPill status={inc.status} />
              </div>
            </button>
          ))}
          {list.length === 0 && !incidents.loading && (
            <EmptyState
              icon={ShieldCheck}
              title="No incidents for this filter"
              hint="Open incidents appear here automatically when an alert rule fires."
            />
          )}
        </div>
      </div>

      {/* ---------------------------------------------------------- detail */}
      <div className="space-y-4">
        {selected ? (
          <div className="card animate-fadeUp">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
                <AlertTriangle size={15} className="text-amber-300" /> {selected.title}
              </h2>
              <div className="flex flex-wrap gap-2">
                {selected.status !== 'resolved' && (
                  <>
                    <button
                      onClick={() => act(() => api.acknowledge(selected.id), `Incident ${selected.public_id} acknowledged`)}
                      className="btn-ghost"
                    >
                      <CheckCircle2 size={14} /> Acknowledge
                    </button>
                    <button
                      onClick={() => act(() => api.resolve(selected.id), `Incident ${selected.public_id} resolved`)}
                      className="btn-ghost"
                    >
                      <ShieldCheck size={14} /> Resolve
                    </button>
                  </>
                )}
                <button onClick={exportIncident} className="btn-ghost">
                  <Download size={14} /> Export JSON
                </button>
              </div>
            </div>
            <RcaPanel incident={selected} />
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="label">Detected</p>
                <p className="mt-1 text-[12px] text-slate-300">{timeAgo(selected.detected_at)}</p>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="label">Last seen</p>
                <p className="mt-1 text-[12px] text-slate-300">{timeAgo(selected.last_seen_at)}</p>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <p className="label">Duration</p>
                <p className="mt-1 text-[12px] text-slate-300">
                  {selected.duration_seconds ? fmtDuration(selected.duration_seconds) : 'ongoing'}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="card">
            <EmptyState icon={AlertTriangle} title="Select an incident" hint="Pick an incident from the console to inspect its root cause analysis." />
          </div>
        )}
      </div>
    </div>
  )
}
