import React from 'react'
import { statusStyle } from '../lib/format'

/* ------------------------------------------------------------------ pills */
export function StatusPill({ status = 'unknown', label, className = '', pulse = false }) {
  const s = statusStyle(status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ring-1 ${s.border} ${s.bg} ${s.text} ${s.ring} ${className}`}
    >
      <span className="relative flex h-1.5 w-1.5">
        {pulse && (
          <span className={`absolute inline-flex h-full w-full rounded-full ${s.dot} animate-pulseRing`} />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${s.dot}`} />
      </span>
      {label ?? s.label}
    </span>
  )
}

export function Badge({ children, className = '' }) {
  return (
    <span className={`chip ${className}`}>{children}</span>
  )
}

/* --------------------------------------------------------------- stat card */
export function StatCard({ icon: Icon, label, value, sub, tone = 'brand', spark, footer, loading }) {
  const tones = {
    brand: 'from-indigo-500/20 to-indigo-500/0 text-indigo-300',
    emerald: 'from-emerald-500/20 to-emerald-500/0 text-emerald-300',
    amber: 'from-amber-500/20 to-amber-500/0 text-amber-300',
    rose: 'from-rose-500/20 to-rose-500/0 text-rose-300',
    cyan: 'from-cyan-500/20 to-cyan-500/0 text-cyan-300',
    violet: 'from-violet-500/20 to-violet-500/0 text-violet-300',
  }
  return (
    <div className="card card-hover overflow-hidden animate-fadeUp">
      <div className={`pointer-events-none absolute inset-x-0 -top-16 h-32 bg-gradient-to-b ${tones[tone]} blur-2xl opacity-60`} />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="label">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-white">
            {loading ? <span className="inline-block h-7 w-20 animate-shimmer rounded bg-white/10" /> : value}
          </p>
          {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
        </div>
        {Icon && (
          <span className="rounded-xl border border-white/10 bg-white/[0.04] p-2 text-slate-300">
            <Icon size={16} />
          </span>
        )}
      </div>
      {spark && <div className="mt-4">{spark}</div>}
      {footer && <div className="mt-3 border-t border-white/[0.06] pt-3 text-[11px] text-slate-400">{footer}</div>}
    </div>
  )
}

/* --------------------------------------------------------------- sparkline */
export function Sparkline({ data = [], width = 120, height = 34, stroke = '#818CF8', fill = true }) {
  const values = data.filter((v) => typeof v === 'number')
  if (values.length < 2) return <div style={{ height }} />
  const max = Math.max(...values)
  const min = Math.min(...values)
  const span = max - min || 1
  const step = width / (values.length - 1)
  const pts = values.map((v, i) => [i * step, height - ((v - min) / span) * (height - 6) - 3])
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${path} L${width},${height} L0,${height} Z`
  const gid = `spark-${Math.random().toString(36).slice(2, 8)}`
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gid})`} />}
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* -------------------------------------------------------------- uptime bar */
export function UptimeStrip({ slots = [], className = '' }) {
  const color = (state) =>
    state === 'up' ? 'bg-emerald-500/80' : state === 'degraded' ? 'bg-amber-500/80' : state === 'down' ? 'bg-rose-500/85' : 'bg-slate-700/60'
  return (
    <div className={`flex h-7 gap-[2px] ${className}`}>
      {slots.length === 0 && (
        <div className="flex-1 rounded bg-slate-700/40" />
      )}
      {slots.map((s, i) => (
        <div
          key={i}
          title={`${s.bucket} · ${s.uptime_pct}% uptime (${s.checks} checks)`}
          className={`group relative flex-1 rounded-[2px] ${color(s.state)} transition hover:scale-y-125`}
        />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------- misc blocks */
export function SectionHeader({ title, subtitle, right }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold tracking-tight text-white">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={`animate-shimmer rounded-md bg-white/[0.06] ${className}`} />
}

export function EmptyState({ icon: Icon, title, hint, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 py-10 text-center">
      {Icon && (
        <span className="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-slate-400">
          <Icon size={18} />
        </span>
      )}
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint && <p className="max-w-md text-xs text-slate-500">{hint}</p>}
      {action}
    </div>
  )
}

export function KeyValue({ label, value, mono = false }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-right text-xs text-slate-200 ${mono ? 'mono' : ''}`}>{value}</span>
    </div>
  )
}

/* ------------------------------------------------------------ chart tooltip */
export function ChartTooltip({ active, payload, label, formatter, labelFormatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-white/10 bg-ink-850/95 px-3 py-2 shadow-xl backdrop-blur">
      <p className="mb-1 text-[11px] font-semibold text-slate-300">
        {labelFormatter ? labelFormatter(label) : label}
      </p>
      <div className="space-y-0.5">
        {payload.map((p, i) => (
          <div key={i} className="flex items-center justify-between gap-6 text-[11px]">
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color || p.stroke }} />
              {p.name}
            </span>
            <span className="font-mono text-slate-100">
              {formatter ? formatter(p.value, p) : p.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- data table */
export function Table({ columns, rows, keyOf, onRowClick, empty }) {
  if (!rows?.length) return empty
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-white/[0.07]">
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 ${c.className || ''}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={keyOf ? keyOf(row, idx) : idx}
              onClick={() => onRowClick?.(row)}
              className={`border-b border-white/[0.04] last:border-0 transition ${onRowClick ? 'cursor-pointer hover:bg-white/[0.035]' : ''}`}
            >
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-2.5 align-middle ${c.cellClassName || ''}`}>
                  {c.render ? c.render(row, idx) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
