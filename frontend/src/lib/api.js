/**
 * Tiny API client for the FastAPI monitoring control plane.
 * All requests go to the same origin; Vite proxies /monitor -> :8000.
 */

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      detail = body?.detail ?? body?.message ?? detail
    } catch {
      /* non JSON error body */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return null
  return res.json()
}

const qs = (params = {}) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : ''
}

export const api = {
  // ---- dashboard reads
  summary: (window = '24h') => request(`/monitor/summary${qs({ window })}`),
  timeseries: (window = '24h', endpointId) => request(`/monitor/timeseries${qs({ window, endpoint_id: endpointId })}`),
  endpoints: (window = '24h') => request(`/monitor/endpoints${qs({ window })}`),
  uptime: (endpointId, hours = 24) => request(`/monitor/endpoints/${endpointId}/uptime${qs({ hours })}`),
  checks: (endpointId, limit = 100) => request(`/monitor/endpoints/${endpointId}/checks${qs({ limit })}`),
  traffic: (window = '24h') => request(`/monitor/traffic${qs({ window })}`),
  incidents: ({ status = 'all', severity = 'all', limit = 50 } = {}) =>
    request(`/monitor/incidents${qs({ status, severity, limit })}`),
  incident: (id) => request(`/monitor/incidents/${id}`),
  alerts: ({ limit = 60, channel = 'all' } = {}) => request(`/monitor/alerts${qs({ limit, channel })}`),
  outbox: (limit = 40) => request(`/monitor/alerts/outbox${qs({ limit })}`),
  errors: (limit = 50) => request(`/monitor/errors${qs({ limit })}`),
  engineStatus: () => request('/monitor/engine/status'),

  // ---- control actions
  probeNow: () => request('/monitor/probe/now', { method: 'POST' }),
  scenarios: () => request('/monitor/scenarios'),
  simulate: (scenario) => request(`/monitor/simulate/${scenario}`, { method: 'POST' }),
  acknowledge: (id) => request(`/monitor/incidents/${id}/acknowledge`, { method: 'POST' }),
  resolve: (id) => request(`/monitor/incidents/${id}/resolve`, { method: 'POST' }),
  settings: () => request('/monitor/settings'),
  updateSettings: (payload) =>
    request('/monitor/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  testNotifications: (channels = 'slack,email,call') =>
    request(`/monitor/notifications/test${qs({ channels })}`, { method: 'POST' }),

  // ---- sample API (used by the explorer)
  callSample: (path, apiKey) =>
    request(path, apiKey ? { headers: { 'X-API-Key': apiKey } } : {}),
}

export default api
