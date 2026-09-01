import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchHealth } from '../api'
import type { Health } from '../types'

const POLL_MS = 5000

/**
 * Loads /api/health, polls it every 5s (so opening Rekordbox after the app is
 * already running gets noticed), and exposes a manual `reload`. `setHealth`
 * lets callers push a fresh health object returned by another endpoint
 * (e.g. /api/db/switch) without waiting for the next poll.
 */
export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null)
  const [reachable, setReachable] = useState(true)
  const timer = useRef<number | undefined>(undefined)

  const reload = useCallback(() => {
    return fetchHealth()
      .then((h) => {
        setHealth(h)
        setReachable(true)
        return h
      })
      .catch(() => {
        setReachable(false)
        return null
      })
  }, [])

  useEffect(() => {
    reload()
    timer.current = window.setInterval(reload, POLL_MS)
    return () => window.clearInterval(timer.current)
  }, [reload])

  return { health, reachable, reload, setHealth }
}
