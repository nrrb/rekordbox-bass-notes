import { useCallback, useEffect, useState } from 'react'
import { dismissUpdate, fetchUpdateCheck } from '../api'
import type { UpdateInfo } from '../types'

/**
 * One-shot update check on mount. `dismiss` hides the banner and remembers the
 * acknowledged version server-side (config.json `last_seen_version`).
 */
export function useUpdateCheck() {
  const [info, setInfo] = useState<UpdateInfo | null>(null)

  useEffect(() => {
    let alive = true
    fetchUpdateCheck()
      .then((i) => {
        if (alive) setInfo(i)
      })
      .catch(() => {
        /* offline / not configured — no banner */
      })
    return () => {
      alive = false
    }
  }, [])

  const dismiss = useCallback(() => {
    setInfo((cur) => {
      if (cur?.latest) dismissUpdate(cur.latest).catch(() => {})
      return cur ? { ...cur, update_available: false } : cur
    })
  }, [])

  return { info, dismiss }
}
