import { useCallback, useEffect, useRef, useState } from 'react'

/** Poll an async fetcher on an interval, with manual refresh support. */
export function useApi(fetcher, deps = [], intervalMs = 0) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const run = useCallback(async () => {
    try {
      const result = await fetcherRef.current()
      if (mounted.current) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (mounted.current) setError(err)
    } finally {
      if (mounted.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    mounted.current = true
    run()
    return () => {
      mounted.current = false
    }
  }, [...deps, run])

  useEffect(() => {
    if (!intervalMs) return undefined
    const id = setInterval(run, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, run, ...deps])

  return { data, error, loading, refresh: run, setData }
}

/** setInterval that can be paused by passing null as the delay. */
export function useInterval(callback, delay) {
  const saved = useRef(callback)
  useEffect(() => {
    saved.current = callback
  }, [callback])
  useEffect(() => {
    if (delay === null || delay === undefined) return undefined
    const id = setInterval(() => saved.current(), delay)
    return () => clearInterval(id)
  }, [delay])
}

/** Toast notifications (simple global-ish store). */
let toastId = 0
const listeners = new Set()

export function pushToast(toast) {
  toastId += 1
  const item = { id: toastId, tone: 'info', duration: 4500, ...toast }
  listeners.forEach((fn) => fn(item))
  setTimeout(() => listeners.forEach((fn) => fn({ ...item, remove: true })), item.duration)
}

export function useToasts() {
  const [toasts, setToasts] = useState([])
  useEffect(() => {
    const handler = (toast) => {
      setToasts((prev) =>
        toast.remove ? prev.filter((t) => t.id !== toast.id) : [...prev.slice(-3), toast],
      )
    }
    listeners.add(handler)
    return () => listeners.delete(handler)
  }, [])
  return toasts
}
