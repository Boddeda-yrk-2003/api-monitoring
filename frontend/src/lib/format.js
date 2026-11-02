/** Formatting helpers. Backend timestamps are naive UTC -> append Z on parse. */

export function parseUtc(value) {
  if (!value) return null
  const s = String(value)
  return new Date(s.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(s) ? s : `${s.replace(' ', 'T')}Z`)
}

export function fmtTime(value) {
  const d = parseUtc(value)
  if (!d) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

export function fmtDateTime(value) {
  const d = parseUtc(value)
  if (!d) return '—'
  return d.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function timeAgo(value) {
  const d = parseUtc(value)
  if (!d) return '—'
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function fmtNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const v = Number(n)
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (Math.abs(v) >= 10_000) return `${(v / 1000).toFixed(1)}k`
  return v.toLocaleString()
}

export function fmtMs(ms) {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '—'
  const v = Number(ms)
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`
  return `${v.toFixed(v < 10 ? 1 : 0)}ms`
}

export function fmtPct(pct, digits = 2) {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return '—'
  return `${Number(pct).toFixed(digits)}%`
}

export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.max(0, Math.round(Number(seconds)))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`
}

export const STATUS_STYLES = {
  healthy: { label: 'Healthy', dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-500/30', bg: 'bg-emerald-500/10', border: 'border-emerald-500/25' },
  degraded: { label: 'Degraded', dot: 'bg-amber-400', text: 'text-amber-300', ring: 'ring-amber-500/30', bg: 'bg-amber-500/10', border: 'border-amber-500/25' },
  down: { label: 'Down', dot: 'bg-rose-500', text: 'text-rose-300', ring: 'ring-rose-500/30', bg: 'bg-rose-500/10', border: 'border-rose-500/25' },
  critical: { label: 'Critical', dot: 'bg-rose-500', text: 'text-rose-300', ring: 'ring-rose-500/30', bg: 'bg-rose-500/10', border: 'border-rose-500/25' },
  warning: { label: 'Warning', dot: 'bg-amber-400', text: 'text-amber-300', ring: 'ring-amber-500/30', bg: 'bg-amber-500/10', border: 'border-amber-500/25' },
  info: { label: 'Info', dot: 'bg-sky-400', text: 'text-sky-300', ring: 'ring-sky-500/30', bg: 'bg-sky-500/10', border: 'border-sky-500/25' },
  paused: { label: 'Not probed', dot: 'bg-slate-500', text: 'text-slate-400', ring: 'ring-slate-500/30', bg: 'bg-slate-500/10', border: 'border-slate-500/25' },
  unknown: { label: 'Unknown', dot: 'bg-slate-500', text: 'text-slate-400', ring: 'ring-slate-500/30', bg: 'bg-slate-500/10', border: 'border-slate-500/25' },
  open: { label: 'Open', dot: 'bg-rose-500', text: 'text-rose-300', ring: 'ring-rose-500/30', bg: 'bg-rose-500/10', border: 'border-rose-500/25' },
  acknowledged: { label: 'Acked', dot: 'bg-amber-400', text: 'text-amber-300', ring: 'ring-amber-500/30', bg: 'bg-amber-500/10', border: 'border-amber-500/25' },
  resolved: { label: 'Resolved', dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-500/30', bg: 'bg-emerald-500/10', border: 'border-emerald-500/25' },
  sent: { label: 'Sent', dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-500/30', bg: 'bg-emerald-500/10', border: 'border-emerald-500/25' },
  simulated: { label: 'Dry-run', dot: 'bg-sky-400', text: 'text-sky-300', ring: 'ring-sky-500/30', bg: 'bg-sky-500/10', border: 'border-sky-500/25' },
  failed: { label: 'Failed', dot: 'bg-rose-500', text: 'text-rose-300', ring: 'ring-rose-500/30', bg: 'bg-rose-500/10', border: 'border-rose-500/25' },
}

export const statusStyle = (key) => STATUS_STYLES[key] ?? STATUS_STYLES.unknown

export const CHANNEL_LABEL = {
  slack: 'Slack',
  email: 'Email',
  call: 'Phone call',
  log: 'Outbox',
}

export function download(filename, content, type = 'application/json') {
  const blob = content instanceof Blob ? content : new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function toCsv(rows) {
  if (!rows?.length) return ''
  const headers = Object.keys(rows[0])
  const esc = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [headers.join(','), ...rows.map((r) => headers.map((h) => esc(r[h])).join(','))].join('\n')
}
