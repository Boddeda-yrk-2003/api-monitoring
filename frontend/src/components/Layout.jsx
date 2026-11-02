import React from 'react'
import {
  Activity,
  AlertTriangle,
  BellRing,
  FlaskConical,
  Github,
  LayoutDashboard,
  Radar,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldCheck,
  TerminalSquare,
  Zap,
} from 'lucide-react'
import { StatusPill } from './ui'
import { pushToast } from '../lib/hooks'
import api from '../lib/api'
import { timeAgo } from '../lib/format'

const NAV = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, hint: 'Health, uptime & performance' },
  { id: 'endpoints', label: 'Endpoints', icon: Radar, hint: 'Per-endpoint SLOs' },
  { id: 'incidents', label: 'Incidents', icon: AlertTriangle, hint: 'Detection & root cause' },
  { id: 'alerts', label: 'Alerts', icon: BellRing, hint: 'Notification channels' },
  { id: 'lab', label: 'Failure Lab', icon: FlaskConical, hint: 'Simulate & verify detection' },
  { id: 'explorer', label: 'API Explorer', icon: TerminalSquare, hint: 'Call the sample API' },
  { id: 'settings', label: 'Settings', icon: SettingsIcon, hint: 'Thresholds & integrations' },
]

export function Sidebar({ page, onNavigate, summary }) {
  return (
    <aside className="hidden w-[248px] shrink-0 flex-col border-r border-white/[0.06] bg-ink-850/60 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="relative">
          <div className="absolute -inset-1 rounded-xl bg-gradient-to-br from-brand-500 to-cyan-400 opacity-40 blur" />
          <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 text-white shadow-lg">
            <ShieldCheck size={18} />
          </div>
        </div>
        <div>
          <p className="text-sm font-semibold tracking-tight text-white">APIGuard</p>
          <p className="text-[11px] text-slate-500">API Monitoring · v1.0.0</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV.map((item) => {
          const Icon = item.icon
          const active = page === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                active
                  ? 'bg-gradient-to-r from-brand-500/20 to-transparent text-white ring-1 ring-inset ring-brand-500/30'
                  : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-100'
              }`}
            >
              <Icon size={16} className={active ? 'text-brand-300' : 'text-slate-500 group-hover:text-slate-300'} />
              <span className="flex-1">
                <span className="block text-[13px] font-medium">{item.label}</span>
                <span className="block text-[10.5px] text-slate-500">{item.hint}</span>
              </span>
              {item.id === 'incidents' && summary?.open_incidents > 0 && (
                <span className="rounded-full bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300 ring-1 ring-rose-500/30">
                  {summary.open_incidents}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      <div className="m-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3">
        <div className="flex items-center justify-between">
          <span className="label">Service</span>
          <StatusPill status={summary?.status ?? 'unknown'} pulse />
        </div>
        <dl className="mt-3 space-y-1.5 text-[11px]">
          <div className="flex justify-between text-slate-400">
            <dt>Uptime (24h)</dt>
            <dd className="font-mono text-slate-200">{summary ? `${summary.uptime_pct?.toFixed(2)}%` : '—'}</dd>
          </div>
          <div className="flex justify-between text-slate-400">
            <dt>Endpoints</dt>
            <dd className="font-mono text-slate-200">
              {summary ? `${summary.endpoints_up}/${summary.endpoints_monitored}` : '—'}
            </dd>
          </div>
          <div className="flex justify-between text-slate-400">
            <dt>Open incidents</dt>
            <dd className="font-mono text-slate-200">{summary?.open_incidents ?? '—'}</dd>
          </div>
        </dl>
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] py-1.5 text-[11px] text-slate-300 hover:bg-white/[0.07]"
        >
          <Github size={12} /> Swagger / OpenAPI
        </a>
      </div>
    </aside>
  )
}

export function MobileNav({ page, onNavigate }) {
  return (
    <div className="sticky top-0 z-20 flex gap-1 overflow-x-auto border-b border-white/[0.06] bg-ink-900/90 px-3 py-2 backdrop-blur lg:hidden">
      {NAV.map((item) => {
        const Icon = item.icon
        const active = page === item.id
        return (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs transition ${
              active ? 'bg-brand-500/20 text-white ring-1 ring-brand-500/30' : 'text-slate-400'
            }`}
          >
            <Icon size={14} /> {item.label}
          </button>
        )
      })}
    </div>
  )
}

export function TopBar({ title, subtitle, window, onWindowChange, onRefresh, refreshing, lastUpdated, children }) {
  const windows = ['15m', '1h', '6h', '24h', '7d']
  return (
    <header className="sticky top-0 z-10 -mx-5 mb-5 border-b border-white/[0.06] bg-ink-900/80 px-5 py-4 backdrop-blur-xl lg:static lg:mx-0 lg:rounded-2xl lg:border lg:px-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-white">{title}</h1>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {children}
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1">
            {windows.map((w) => (
              <button
                key={w}
                onClick={() => onWindowChange?.(w)}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
                  window === w ? 'bg-brand-500/25 text-white ring-1 ring-brand-500/40' : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {w}
              </button>
            ))}
          </div>
          <span className="hidden items-center gap-1.5 text-[11px] text-slate-500 sm:flex">
            <Activity size={12} className="text-emerald-400" />
            {lastUpdated ? `updated ${timeAgo(lastUpdated)}` : 'live'}
          </span>
          <button onClick={onRefresh} className="btn-ghost px-2.5 py-2" title="Refresh now">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
    </header>
  )
}

export function ProbeButton({ onDone }) {
  const [busy, setBusy] = React.useState(false)
  const run = async () => {
    setBusy(true)
    try {
      const res = await api.probeNow()
      pushToast({ tone: 'success', title: `Probe cycle complete`, message: `${res.ran} endpoints checked in ${Math.round(res.duration_ms)} ms` })
      onDone?.()
    } catch (err) {
      pushToast({ tone: 'error', title: 'Probe failed', message: err.message })
    } finally {
      setBusy(false)
    }
  }
  return (
    <button onClick={run} disabled={busy} className="btn-ghost">
      <Zap size={14} className={busy ? 'animate-pulse text-amber-300' : 'text-amber-300'} />
      {busy ? 'Probing…' : 'Run probe now'}
    </button>
  )
}

export function Toasts({ toasts }) {
  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-[320px] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto animate-fadeUp rounded-xl border px-4 py-3 shadow-2xl backdrop-blur-xl ${
            t.tone === 'success'
              ? 'border-emerald-500/30 bg-emerald-500/10'
              : t.tone === 'error'
                ? 'border-rose-500/30 bg-rose-500/10'
                : 'border-white/10 bg-ink-800/90'
          }`}
        >
          <p className="text-[13px] font-semibold text-white">{t.title}</p>
          {t.message && <p className="mt-0.5 text-[11.5px] leading-relaxed text-slate-300">{t.message}</p>}
        </div>
      ))}
    </div>
  )
}
