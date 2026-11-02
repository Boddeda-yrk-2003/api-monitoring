import React from 'react'
import { Badge, KeyValue, StatusPill } from './ui'
import { CHANNEL_LABEL, fmtDateTime, fmtDuration, fmtMs, timeAgo } from '../lib/format'
import { Brain, ClipboardList, Crosshair, Hash, Lightbulb, Search, ShieldAlert, Terminal, Users } from 'lucide-react'

const EVIDENCE_LABELS = {
  http_status: 'HTTP status',
  error_type: 'Error type',
  latency_ms: 'Latency (ms)',
  latency_threshold_ms: 'Latency SLO (ms)',
  exception_type: 'Exception type',
  exception_message: 'Exception message',
  failing_frames: 'Failing frames',
  request_id: 'Request id',
  path: 'Path',
  method: 'Method',
  source: 'Detection source',
  detection_time_utc: 'Detected at (UTC)',
  error_rate_pct: 'Error rate (%)',
  error_rate_threshold_pct: 'Error rate threshold (%)',
  transport_error: 'Transport error',
  retry_after_hint: 'Retry hint',
  expected_header: 'Expected header',
  rule: 'Rule description',
  consecutive_failures: 'Consecutive failures',
  occurrences: 'Occurrences in window',
  timeout_budget_ms: 'Timeout budget (ms)',
  seeded: 'Seeded demo record',
  detection: 'Detection method',
}

function Block({ icon: Icon, title, tone = 'text-slate-300', children, right }) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className={`flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider ${tone}`}>
          {Icon && <Icon size={13} />} {title}
        </h4>
        {right}
      </div>
      {children}
    </div>
  )
}

export default function RcaPanel({ incident, compact = false }) {
  if (!incident) return null
  const evidence = incident.evidence ?? {}
  const traceback = evidence.traceback
  const evidenceEntries = Object.entries(evidence).filter(
    ([k, v]) => k !== 'traceback' && v !== null && v !== undefined && v !== '' && v !== false,
  )

  return (
    <div className="space-y-3">
      {/* header */}
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={incident.severity} />
        <StatusPill status={incident.status} />
        <Badge>
          <Hash size={10} className="text-slate-500" /> {incident.public_id}
        </Badge>
        <Badge>
          <Crosshair size={10} className="text-slate-500" /> {incident.rule_id}
        </Badge>
        <Badge>
          <Terminal size={10} className="text-slate-500" /> {incident.endpoint_path}
        </Badge>
        {incident.http_status ? (
          <Badge>
            HTTP {incident.http_status}
          </Badge>
        ) : null}
        <span className="ml-auto text-[11px] text-slate-500">
          detected {timeAgo(incident.detected_at)} · {fmtDateTime(incident.detected_at)}
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          {/* root cause */}
          <Block icon={Brain} title="Root cause analysis" tone="text-rose-300">
            <p className="text-[13px] leading-relaxed text-slate-200">{incident.root_cause}</p>
            <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5">
                <ShieldAlert size={11} /> confidence:
                <span className="font-medium text-slate-300">{incident.root_cause_confidence}</span>
              </span>
              <span className="flex items-center gap-1.5">
                <Users size={11} /> owner:
                <span className="font-medium text-slate-300">{incident.owner_team}</span>
              </span>
              <span>category: <span className="font-medium text-slate-300">{incident.category}</span></span>
              <span>occurrences: <span className="font-medium text-slate-300">{incident.occurrences}</span></span>
              {incident.duration_seconds !== null && incident.duration_seconds !== undefined && (
                <span>duration: <span className="font-medium text-slate-300">{fmtDuration(incident.duration_seconds)}</span></span>
              )}
            </div>
          </Block>

          {/* probable causes */}
          <Block icon={Search} title="Probable causes">
            <ul className="space-y-1.5">
              {(incident.probable_causes ?? []).map((c, i) => (
                <li key={i} className="flex gap-2 text-[12.5px] text-slate-300">
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-slate-600" />
                  {c}
                </li>
              ))}
            </ul>
          </Block>

          {/* recommended actions */}
          <Block icon={Lightbulb} title="Recommended actions" tone="text-emerald-300">
            <ol className="space-y-1.5">
              {(incident.recommended_actions ?? []).map((a, i) => (
                <li key={i} className="flex gap-2.5 text-[12.5px] text-slate-300">
                  <span className="grid h-4.5 w-4.5 min-w-[18px] place-items-center rounded bg-emerald-500/15 text-[10px] font-semibold text-emerald-300">
                    {i + 1}
                  </span>
                  {a}
                </li>
              ))}
            </ol>
          </Block>
        </div>

        {/* evidence */}
        <div className="space-y-3">
          <Block icon={ClipboardList} title="Captured evidence">
            <div className="divide-y divide-white/[0.05]">
              <KeyValue label="Latency" value={fmtMs(incident.latency_ms)} mono />
              {evidenceEntries.map(([k, v]) => (
                <KeyValue
                  key={k}
                  label={EVIDENCE_LABELS[k] ?? k.replace(/_/g, ' ')}
                  value={typeof v === 'object' ? JSON.stringify(v) : String(v)}
                  mono={typeof v === 'number' || /id|frames|time/i.test(k)}
                />
              ))}
            </div>
          </Block>

          {traceback && (
            <Block icon={Terminal} title="Stack trace">
              <pre className="max-h-52 overflow-auto rounded-lg border border-white/[0.07] bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-rose-200/90">
                {traceback}
              </pre>
            </Block>
          )}

          {incident.channels?.length > 0 && (
            <Block icon={Crosshair} title="Notifications dispatched">
              <div className="flex flex-wrap gap-1.5">
                {incident.channels.map((c) => (
                  <Badge key={c}>{CHANNEL_LABEL[c] ?? c}</Badge>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                {incident.alert_count} notification(s) recorded in the alert outbox.
              </p>
            </Block>
          )}
        </div>
      </div>
    </div>
  )
}
