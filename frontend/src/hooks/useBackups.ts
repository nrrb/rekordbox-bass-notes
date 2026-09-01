import { useCallback, useEffect, useState } from 'react'
import { fetchBackups } from '../api'
import type { BackupsResponse } from '../types'

export function useBackups(enabled: boolean) {
  const [data, setData] = useState<BackupsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    return fetchBackups()
      .then((d) => setData(d))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (enabled) reload()
  }, [enabled, reload])

  return { data, loading, error, reload }
}
