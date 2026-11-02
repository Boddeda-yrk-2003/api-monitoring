import React from 'react'
import { Database, Save, Server, SlidersHorizontal, Waypoints } from 'lucide-react'
import api from '../lib/api'
import { pushToast, useApi } from '../lib/hooks'
import { Badge, KeyValue, SectionHeader, Skeleton, StatusPill } from '../components/ui'

const THRESHOLDS = [
  { key: 'latency_threshold_ms', label: 'Latency alert threshold (ms)', hint: 'Fires SLOW_RESPONSE when a response exceeds this value', step: 100 },
  { key: 'error_rate_threshold_pct', label: 'Error rate threshold (%)', hint: 'Fires HIGH_ERROR_RATE over the rolling window', step: 0.5 },
  { key: 'error_rate_window_minutes', label: 'Error-rate window (minutes)', hint: 'Rolling window used to compute the failure rate', step: 1 },
  { key: 'downtime_consecutive_failures', label: 'Downtime threshold (consecutive failures)', hint: 'Failures before an endpoint is marked DOWN', step: 1 },
  { key: 'recovery_consecutive_successes', label: 'Recovery threshold (consecutive successes)', hint: 'Successes before an incident auto-resolves', step: 1 },
  { key: 'alert_cooldown_seconds', label: 'Alert cooldown (seconds)', hint: 'De-duplication window per rule + endpoint', step: 10 },
  { key: 'probe_interval_seconds', label: 'Probe interval (seconds)', hint: 'How often the synthetic monitor runs', step: 5 },
  { key: 'rate_limit_max_requests', label: 'Rate limit quota (requests / window)', hint: 'Used by /simulate-rate-limit', step: 1 },
  { key: 'simulated_timeout_seconds', label: 'Simulated slow response (seconds)', hint: 'Default sleep for /simulate-timeout', step: 0.5 },
]

const CHANNEL_FIELDS = [
  { key: 'slack_webhook_url', label: 'Slack incoming webhook URL', placeholder: 'https://hooks.slack.com/services/…', secret: true },
  { key: 'slack_channel_label', label: 'Slack channel label', placeholder: '#api-alerts' },
  { key: 'alert_email_to', label: 'Alert recipient e-mail', placeholder: 'sre-oncall@example.com' },
  { key: 'alert_email_from', label: 'Alert sender e-mail', placeholder: 'apiguard-alerts@example.com' },
  { key: 'smtp_host', label: 'SMTP host', placeholder: 'smtp.gmail.com' },
  { key: 'smtp_port', label: 'SMTP port', placeholder: '587' },
  { key: 'smtp_username', label: 'SMTP username', placeholder: '' },
  { key: 'smtp_password', label: 'SMTP password / app token', placeholder: '••••••••', secret: true },
  { key: 'twilio_account_sid', label: 'Twilio account SID (voice alert)', placeholder: 'AC…', secret: true },
  { key: 'twilio_auth_token', label: 'Twilio auth token', placeholder: '••••••••', secret: true },
  { key: 'twilio_from_number', label: 'Twilio from number', placeholder: '+1555…' },
  { key: 'alert_call_to_number', label: 'On-call number to call', placeholder: '+91…' },
]

function Field({ label, hint, children }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
      <label className="block text-[12px] font-medium text-slate-200">{label}</label>
      {hint && <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p>}
      <div className="mt-2">{children}</div>
    </div>
  )
}

const inputCls =
  'w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-[12px] text-slate-200 outline-none transition focus:border-brand-500/60'

export default function Settings() {
  const settings = useApi(() => api.settings(), [], 0)
  const engine = useApi(() => api.engineStatus(), [], 10000)
  const [form, setForm] = React.useState({})
  const [saving, setSaving] = React.useState(false)

  const value = (key) => form[key] ?? settings.data?.[key] ?? ''
  const set = (key, v) => setForm((prev) => ({ ...prev, [key]: v }))

  const save = async (keys) => {
    const payload = {}
    keys.forEach((k) => {
      const v = value(k)
      if (v !== '' && v !== undefined && v !== null) payload[k] = v
    })
    if (!Object.keys(payload).length) {
      pushToast({ tone: 'info', title: 'Nothing to save' })
      return
    }
    setSaving(true)
    try {
      await api.updateSettings(payload)
      pushToast({ tone: 'success', title: 'Configuration updated', message: `${Object.keys(payload).length} setting(s) applied at runtime.` })
      settings.refresh()
    } catch (err) {
      pushToast({ tone: 'error', title: 'Save failed', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  if (settings.loading && !settings.data) return <Skeleton className="h-96 w-full" />

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------------- engine */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card card-hover animate-fadeUp">
          <div className="flex items-center justify-between">
            <span className="label">Monitor engine</span>
            <StatusPill status={engine.data?.running ? 'healthy' : 'down'} pulse={engine.data?.running} />
          </div>
          <p className="mt-2 text-[13px] text-slate-200">
            {engine.data?.running ? `Probing every ${engine.data?.interval_seconds}s` : 'Stopped'}
          </p>
          <div className="mt-3">
            <KeyValue label="Cycles executed" value={engine.data?.cycles ?? '—'} mono />
            <KeyValue label="Last cycle duration" value={`${engine.data?.last_cycle_duration_ms ?? '—'} ms`} mono />
            <KeyValue label="Last cycle" value={engine.data?.last_cycle_at ?? '—'} mono />
          </div>
        </div>

        <div className="card card-hover animate-fadeUp">
          <div className="flex items-center justify-between">
            <span className="label">Storage</span>
            <Database size={14} className="text-brand-300" />
          </div>
          <p className="mt-2 text-[13px] text-slate-200">SQLite</p>
          <div className="mt-3">
            <KeyValue label="File" value="backend/data/apiguard.db" mono />
            <KeyValue label="ORM" value="SQLAlchemy 2.0" mono />
            <KeyValue label="Tables" value="endpoints, checks, request_logs, error_logs, incidents, alerts, settings_kv" mono />
          </div>
        </div>

        <div className="card card-hover animate-fadeUp">
          <div className="flex items-center justify-between">
            <span className="label">Integrations</span>
            <Waypoints size={14} className="text-brand-300" />
          </div>
          <p className="mt-2 text-[13px] text-slate-200">Prometheus · Grafana</p>
          <div className="mt-3">
            <KeyValue label="Scrape target" value="GET /metrics" mono />
            <KeyValue label="Exporter" value="prometheus_client" mono />
            <KeyValue label="Dashboard API" value="GET /monitor/*" mono />
          </div>
        </div>
      </div>

      {/* --------------------------------------------------- thresholds */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Alert thresholds"
          subtitle="Applied immediately — no restart required"
          right={
            <button onClick={() => save(THRESHOLDS.map((t) => t.key))} disabled={saving} className="btn-primary">
              <Save size={14} /> Save thresholds
            </button>
          }
        />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {THRESHOLDS.map((t) => (
            <Field key={t.key} label={t.label} hint={t.hint}>
              <input
                type="number"
                step={t.step}
                value={value(t.key)}
                onChange={(e) => set(t.key, e.target.value)}
                className={inputCls}
              />
            </Field>
          ))}
        </div>
      </div>

      {/* ----------------------------------------------------- channels */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Notification channels"
          subtitle="Leave a field empty to keep that channel in dry-run mode (payload rendered + stored, nothing sent)"
          right={
            <button onClick={() => save(CHANNEL_FIELDS.map((c) => c.key))} disabled={saving} className="btn-primary">
              <Save size={14} /> Save channels
            </button>
          }
        />
        <div className="mb-3 flex flex-wrap gap-2">
          <Badge>Slack: <span className={settings.data?.channels?.slack ? 'text-emerald-300' : 'text-sky-300'}>{settings.data?.channels?.slack ? 'live' : 'dry-run'}</span></Badge>
          <Badge>Email: <span className={settings.data?.channels?.email ? 'text-emerald-300' : 'text-sky-300'}>{settings.data?.channels?.email ? 'live' : 'dry-run'}</span></Badge>
          <Badge>Call: <span className={settings.data?.channels?.call ? 'text-emerald-300' : 'text-sky-300'}>{settings.data?.channels?.call ? 'live' : 'dry-run'}</span></Badge>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {CHANNEL_FIELDS.map((c) => (
            <Field key={c.key} label={c.label}>
              <input
                type={c.secret ? 'password' : 'text'}
                value={value(c.key)}
                placeholder={c.placeholder}
                onChange={(e) => set(c.key, e.target.value)}
                className={inputCls}
              />
            </Field>
          ))}
        </div>
      </div>

      {/* -------------------------------------------------------- rules */}
      <div className="card animate-fadeUp">
        <SectionHeader
          title="Active alert rules"
          subtitle="Evaluated on every probe cycle and on every live traffic failure"
          right={<Server size={14} className="text-slate-500" />}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead>
              <tr className="border-b border-white/[0.07]">
                {['Rule', 'Trigger condition', 'Severity', 'Channels'].map((h) => (
                  <th key={h} className="px-3 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                ['API_DOWN', `${settings.data?.downtime_consecutive_failures ?? 2} consecutive probe failures or transport error`, 'critical', 'Slack + Email + Call'],
                ['SERVER_ERROR', 'HTTP 5xx on any monitored endpoint', 'critical', 'Slack + Email + Call'],
                ['TIMEOUT', 'Request exceeds the timeout budget (408/504/aborted)', 'critical', 'Slack + Email + Call'],
                ['HEALTH_CHECK_FAILED', '/health does not report healthy', 'critical', 'Slack + Email + Call'],
                ['SLOW_RESPONSE', `Latency > ${settings.data?.latency_threshold_ms ?? 3000} ms`, 'warning', 'Slack + Email'],
                ['HIGH_ERROR_RATE', `Error rate > ${settings.data?.error_rate_threshold_pct ?? 5}% over ${settings.data?.error_rate_window_minutes ?? 5} min`, 'warning', 'Slack + Email'],
                ['AUTH_FAILURE', 'HTTP 401/403 — missing or invalid credentials', 'warning', 'Slack + Email'],
                ['RATE_LIMIT', 'HTTP 429 — request quota exhausted', 'warning', 'Slack + Email'],
              ].map(([rule, cond, sev, ch]) => (
                <tr key={rule} className="border-b border-white/[0.04] last:border-0">
                  <td className="px-3 py-2 font-mono text-[11.5px] text-brand-200">{rule}</td>
                  <td className="px-3 py-2 text-slate-300">{cond}</td>
                  <td className="px-3 py-2"><StatusPill status={sev} /></td>
                  <td className="px-3 py-2 text-slate-400">{ch}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
