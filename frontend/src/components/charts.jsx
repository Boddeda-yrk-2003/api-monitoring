import React from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartTooltip } from './ui'
import { fmtMs, fmtNumber, fmtPct, fmtTime } from '../lib/format'

const axisProps = {
  stroke: 'rgba(148,163,184,0.25)',
  tickLine: false,
  axisLine: false,
  tick: { fontSize: 11, fill: '#64748b' },
}

const STATUS_COLORS = {
  200: '#34D399',
  401: '#FBBF24',
  403: '#F59E0B',
  404: '#60A5FA',
  429: '#A78BFA',
  500: '#FB7185',
  503: '#F43F5E',
}
const fallbackColor = (code) => STATUS_COLORS[code] ?? (code >= 500 ? '#FB7185' : code >= 400 ? '#FBBF24' : '#34D399')

/* -------------------------------------------------- latency + error trend */
export function LatencyChart({ data = [], height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="gradAvg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#22D3EE" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(148,163,184,0.10)" vertical={false} />
        <XAxis dataKey="bucket" tickFormatter={fmtTime} minTickGap={40} {...axisProps} />
        <YAxis yAxisId="left" tickFormatter={(v) => `${Math.round(v)}ms`} {...axisProps} />
        <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v}`} {...axisProps} />
        <Tooltip
          content={<ChartTooltip labelFormatter={(l) => fmtTime(l)} formatter={(v, p) => (p.dataKey === 'failed' ? fmtNumber(v) : fmtMs(v))} />}
          cursor={{ stroke: 'rgba(148,163,184,0.25)' }}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} iconType="circle" iconSize={7} />
        <Bar yAxisId="right" dataKey="failed" name="Failed checks" fill="#FB7185" fillOpacity={0.35} radius={[3, 3, 0, 0]} barSize={8} />
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="avg_latency_ms"
          name="Avg latency"
          stroke="#22D3EE"
          strokeWidth={2}
          fill="url(#gradAvg)"
        />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="p95_latency_ms"
          name="p95 latency"
          stroke="#A78BFA"
          strokeWidth={1.8}
          dot={false}
        />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="max_latency_ms"
          name="Max latency"
          stroke="#475569"
          strokeWidth={1}
          strokeDasharray="4 4"
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/* ------------------------------------------------- request volume by state */
export function RequestsChart({ data = [], height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="gradOk" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#34D399" stopOpacity={0.6} />
            <stop offset="100%" stopColor="#34D399" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(148,163,184,0.10)" vertical={false} />
        <XAxis dataKey="bucket" tickFormatter={fmtTime} minTickGap={40} {...axisProps} />
        <YAxis tickFormatter={(v) => fmtNumber(v)} {...axisProps} />
        <Tooltip
          content={<ChartTooltip labelFormatter={(l) => fmtTime(l)} formatter={(v) => fmtNumber(v)} />}
          cursor={{ fill: 'rgba(148,163,184,0.06)' }}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} iconType="circle" iconSize={7} />
        <Area type="monotone" dataKey="success" name="Successful" stroke="#34D399" strokeWidth={1.6} fill="url(#gradOk)" />
        <Bar dataKey="failed" name="Failed" stackId="a" fill="#FB7185" fillOpacity={0.75} radius={[3, 3, 0, 0]} barSize={7} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/* ------------------------------------------------------ status donut */
export function StatusDonut({ data = [], height = 220 }) {
  const total = data.reduce((acc, d) => acc + d.count, 0) || 1
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="label"
            innerRadius="62%"
            outerRadius="86%"
            paddingAngle={2}
            stroke="none"
          >
            {data.map((entry) => (
              <Cell key={entry.status_code} fill={fallbackColor(entry.status_code)} fillOpacity={0.85} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip formatter={(v) => fmtNumber(v)} />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold text-white">{fmtNumber(total)}</span>
        <span className="text-[10px] uppercase tracking-widest text-slate-500">requests</span>
      </div>
    </div>
  )
}

export function StatusLegend({ data = [] }) {
  const total = data.reduce((acc, d) => acc + d.count, 0) || 1
  return (
    <ul className="mt-2 space-y-1.5">
      {data.map((d) => (
        <li key={d.status_code} className="flex items-center justify-between text-[11.5px]">
          <span className="flex items-center gap-2 text-slate-400">
            <span className="h-2 w-2 rounded-full" style={{ background: fallbackColor(d.status_code) }} />
            {d.label}
          </span>
          <span className="font-mono text-slate-300">
            {fmtNumber(d.count)} · {fmtPct((d.count / total) * 100, 1)}
          </span>
        </li>
      ))}
    </ul>
  )
}
