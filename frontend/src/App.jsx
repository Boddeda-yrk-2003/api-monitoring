import React from 'react'
import { MobileNav, ProbeButton, Sidebar, Toasts, TopBar } from './components/Layout'
import Overview from './pages/Overview'
import Endpoints from './pages/Endpoints'
import Incidents from './pages/Incidents'
import Alerts from './pages/Alerts'
import FailureLab from './pages/FailureLab'
import Explorer from './pages/Explorer'
import Settings from './pages/Settings'
import api from './lib/api'
import { useApi, useToasts } from './lib/hooks'

const PAGES = {
  overview: {
    title: 'Monitoring overview',
    subtitle: 'Availability, latency, traffic volume and failure trends across the API estate',
    component: Overview,
  },
  endpoints: {
    title: 'Endpoints',
    subtitle: 'Per-endpoint SLOs, uptime history and raw probe results',
    component: Endpoints,
  },
  incidents: {
    title: 'Incidents & root cause analysis',
    subtitle: 'Detected failures with classification, evidence and remediation plan',
    component: Incidents,
  },
  alerts: {
    title: 'Alerts & notifications',
    subtitle: 'Delivery history, channel configuration and captured payloads',
    component: Alerts,
  },
  lab: {
    title: 'Failure lab',
    subtitle: 'Trigger real failures and verify detection, alerting and RCA end to end',
    component: FailureLab,
  },
  explorer: {
    title: 'API explorer',
    subtitle: 'Call the sample API and watch the traffic land in the monitoring pipeline',
    component: Explorer,
  },
  settings: {
    title: 'Settings',
    subtitle: 'Thresholds, notification channels and the active alert-rule catalogue',
    component: Settings,
  },
}

const hashToPage = () => {
  const h = window.location.hash.replace('#', '')
  return PAGES[h] ? h : 'overview'
}

export default function App() {
  const [page, setPage] = React.useState(hashToPage())
  const [window_, setWindow] = React.useState('24h')
  const [nonce, setNonce] = React.useState(0)
  const [refreshing, setRefreshing] = React.useState(false)
  const toasts = useToasts()

  const summary = useApi(() => api.summary(window_), [window_, nonce], 15000)

  React.useEffect(() => {
    const onHash = () => setPage(hashToPage())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = (id) => {
    window.location.hash = id
    setPage(id)
  }

  const refresh = async () => {
    setRefreshing(true)
    await summary.refresh()
    setNonce((n) => n + 1)
    setTimeout(() => setRefreshing(false), 400)
  }

  const meta = PAGES[page]
  const PageComponent = meta.component

  return (
    <div className="relative z-10 flex min-h-screen">
      <Sidebar page={page} onNavigate={navigate} summary={summary.data} />

      <main className="flex-1 px-5 pb-10 pt-4 lg:px-8">
        <MobileNav page={page} onNavigate={navigate} />
        <TopBar
          title={meta.title}
          subtitle={meta.subtitle}
          window={window_}
          onWindowChange={setWindow}
          onRefresh={refresh}
          refreshing={refreshing}
          lastUpdated={summary.data?.generated_at}
        >
          <ProbeButton onDone={refresh} />
        </TopBar>

        <PageComponent key={`${page}-${nonce}`} window={window_} onNavigate={navigate} />

        <footer className="mt-10 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-5 text-[11px] text-slate-600">
          <span>APIGuard · FastAPI + React + SQLite monitoring reference implementation</span>
          <span className="flex items-center gap-3">
            <a className="hover:text-slate-400" href="/docs" target="_blank" rel="noreferrer">Swagger</a>
            <a className="hover:text-slate-400" href="/metrics" target="_blank" rel="noreferrer">Prometheus metrics</a>
            <a className="hover:text-slate-400" href="/monitor/summary" target="_blank" rel="noreferrer">Monitoring API</a>
          </span>
        </footer>
      </main>

      <Toasts toasts={toasts} />
    </div>
  )
}
