import { useCallback, useState } from 'react'
import { analyzeTrack } from '../api'
import type { AnalyzeResponse } from '../types'

export function useAnalyze() {
  const [data, setData] = useState<AnalyzeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const analyze = useCallback((id: string) => {
    setLoading(true)
    setError(null)
    setData(null)
    analyzeTrack(id)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  const reset = useCallback(() => {
    setData(null)
    setError(null)
    setLoading(false)
  }, [])

  return { data, loading, error, analyze, reset }
}
