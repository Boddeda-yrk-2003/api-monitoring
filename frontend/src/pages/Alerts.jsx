import React from 'react'
import { BellRing, Bug, FileJson, Mail, Phone, Send, Slack, Terminal } from 'lucide-react'
import api from '../lib/api'
import { pushToast, useApi } from '../lib/hooks'
import { Badge, EmptyState, SectionHeader, Skeleton, StatusPill } from '../components/ui'
import { CHANNEL_LABEL, fmtDateTime, timeAgo } from '../lib/format'

const CHANNEL_ICON = { slack: Slack, email: Mail, call: Phone, log: FileJson }

function Modal({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-2xl border border-white/10 bg-ink-850 p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-slate-300 hover:bg-white/[0.06]">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function ChannelCard({ channel, label, icon: Icon, configured, destination, onTest, testing }) {
  return (
    <div className="card card-hover animate-fadeUp">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <span className="rounded-xl border border-white/10 bg-white/[0.04] p-2 text-slate-300">
            <Icon size={16} />
          </span>
          <div>
            <p className="text-[13px] font-semibold text-white">{label}</p>
            <p className="text-[11px] text-slate-500">{configured ? 'credentials configured' : 'dry-run mode'}</p>
          </div>
        </div>
        <StatusPill status={configured ? 'healthy' : 'info'} label={configured ? 'Live' : 'Dry-run'} />
      </div>
      <p className="mt-3 truncate rounded-lg border border-white/[0.06] bg-black/20 px-2.5 py-2 font-mono text-[11px] text-slate-400">
        {destination}
      </p>
      <button onClick={onTest} disabled={testing} className="btn-ghost mt-3 w-full">
        <Send size={13} /> {testing ? 'Sending…' : 'Send test alert'}
      </button>
    </div>
  )
}

export default function Alerts() {
  const [channel, setChannel] = React.useState('all')
  const [detail, setDetail] = React.useState(null)
  const [errorDetail, setErrorDetail] = React.useState(null)
  const [testing, setTesting] = React.useState(null)

  const alerts = useApi(() => api.alerts({ limit: 100, channel }), [channel], 15000)
  const settings = useApi(() => api.settings(), [], 60000)
  const outbox = useApi(() => api.outbox(40), [], 30000)
  const errors = useApi(() => api.errors(30), [], 30000)

  const test = async (ch) => {
    setTesting(ch)
    try {
      const results = await api.testNotifications(ch)
      const r = results?.[0]
      pushToast({
        tone: r?.status === 'failed' ? 'error' : 'success',
        title: `${CHANNEL_LABEL[ch]} test ${r?.status ?? 'done'}`,
        message: r?.delivery_note || r?.note || 'Rendered payload stored in the alert outbox.',
      })
      alerts.refresh()
      outbox.refresh()
    } catch (err) {
      pushToast({ tone: 'error', title: 'Test failed', message: err.message })
    } finally {
      setTesting(null)
    }
  }

  const channels = [
    { id: 'slack', label: 'Slack', icon: Slack, configured: settings.data?.channels?.slack, destination: settings.data?.channel_targets?.slack },
    { id: 'email', label: 'Email (SMTP)', icon: Mail, configured: settings.data?.channels?.email, destination: settings.data?.channel_targets?.email },
    { id: 'call', label: 'Phone call (Twilio)', icon: Phone, configured: settings.data?.channels?.call, destination: settings.data?.channel_targets?.call },
  ]

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------- channels */}
      <div>
        <SectionHeader
          title="Notification channels"
          subtitle="Channels without credentials run in dry-run mode: the payload is fully rendered and stored as delivery proof."
        />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {settings.loading && !settings.data
            ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-40 w-full" />)
            : channels.map((c) => (
                <ChannelCard
                  key={c.id}
                  {...c}
                  testing={testing === c.id}
                  onTest={() => test(c.id)}
                />
              ))}
        </div>
        <button onClick={() => test('slack,email,call')} disabled={!!testing} className="btn-primary mt-3">
          <BellRing size={14} /> Test all channels
        </button>
      </div>

      {/* --------------------------------------------------------- alerts */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Alert history"
          subtitle="Every notification attempt with its exact provider payload"
          right={
            <div className="flex items-center gap-1">
              {['all', 'slack', 'email', 'call'].map((c) => (
                <button
                  key={c}
                  onClick={() => setChannel(c)}
                  className={`rounded-lg px-2 py-1 text-[11px] font-medium capitalize transition ${
                    channel === c ? 'bg-brand-500/20 text-white ring-1 ring-brand-500/40' : 'text-slate-400 hover:bg-white/[0.05]'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead>
              <tr className="border-b border-white/[0.07]">
                {['Time', 'Channel', 'Incident', 'Subject', 'Destination', 'Status', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(alerts.data ?? []).map((a) => {
                const Icon = CHANNEL_ICON[a.channel] ?? FileJson
                return (
                  <tr key={a.id} className="border-b border-white/[0.04] transition last:border-0 hover:bg-white/[0.03]">
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-slate-400" title={fmtDateTime(a.created_at)}>
                      {timeAgo(a.created_at)}
                    </td>
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-1.5 text-slate-300">
                        <Icon size={13} /> {CHANNEL_LABEL[a.channel] ?? a.channel}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-500">{a.incident_title ? `#${a.incident_id}` : '—'}</td>
                    <td className="max-w-[280px] truncate px-3 py-2 text-slate-200">{a.subject}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-500">{a.destination}</td>
                    <td className="px-3 py-2"><StatusPill status={a.status} /></td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => setDetail(a)} className="text-[11px] text-brand-300 hover:text-brand-200">
                        payload
                      </button>
                    </td>
                  </tr>
                )
              })}
              {(alerts.data ?? []).length === 0 && !alerts.loading && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState icon={BellRing} title="No alerts yet" hint="Run a failure scenario or send a test alert." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {outbox.data && (
          <p className="mt-3 flex items-center gap-1.5 border-t border-white/[0.06] pt-3 text-[11px] text-slate-500">
            <FileJson size={11} /> Local outbox: <span className="font-mono">{outbox.data.file}</span> · {outbox.data.count} records
          </p>
        )}
      </div>

      {/* ------------------------------------------------ captured errors */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Captured exceptions"
          subtitle="Server-side tracebacks used by the RCA engine (evidence table `error_logs`)"
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead>
              <tr className="border-b border-white/[0.07]">
                {['Time', 'Path', 'Exception', 'Message', 'Request id', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(errors.data ?? []).map((e) => (
                <tr key={e.id} className="border-b border-white/[0.04] last:border-0">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-slate-400">{timeAgo(e.ts)}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-300">{e.path}</td>
                  <td className="px-3 py-2"><Badge className="text-rose-300"><Bug size={10} /> {e.exception_type}</Badge></td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-slate-400">{e.exception_message}</td>
                  <td className="px-3 py-2 font-mono text-[10.5px] text-slate-600">{e.request_id}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => setErrorDetail(e)} className="text-[11px] text-brand-300 hover:text-brand-200">
                      traceback
                    </button>
                  </td>
                </tr>
              ))}
              {(errors.data ?? []).length === 0 && !errors.loading && (
                <tr>
                  <td colSpan={6}>
                    <EmptyState icon={Terminal} title="No exceptions captured" hint="Trigger the HTTP 500 scenario to capture a stack trace." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Alert payload · ${CHANNEL_LABEL[detail?.channel] ?? ''}`}>
        {detail && (
          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 text-[12px]">
                <p className="label">Destination</p>
                <p className="mt-1 font-mono text-slate-200">{detail.destination}</p>
              </div>
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 text-[12px]">
                <p className="label">Delivery status</p>
                <p className="mt-1 text-slate-200">{detail.status} — {detail.delivery_note}</p>
              </div>
            </div>
            {detail.subject && (
              <div>
                <p className="label mb-1">Subject</p>
                <p className="rounded-lg border border-white/[0.07] bg-black/30 p-3 text-[12px] text-slate-200">{detail.subject}</p>
              </div>
            )}
            <div>
              <p className="label mb-1">Body</p>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-white/[0.07] bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
                {detail.body}
              </pre>
            </div>
            <div>
              <p className="label mb-1">Raw provider payload</p>
              <pre className="max-h-72 overflow-auto rounded-lg border border-white/[0.07] bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-emerald-200/80">
                {JSON.stringify(detail.payload, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!errorDetail} onClose={() => setErrorDetail(null)} title="Captured stack trace">
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border border-white/[0.07] bg-black/50 p-4 font-mono text-[11.5px] leading-relaxed text-rose-200/90">
          {errorDetail?.traceback}
        </pre>
      </Modal>
    </div>
  )
}
