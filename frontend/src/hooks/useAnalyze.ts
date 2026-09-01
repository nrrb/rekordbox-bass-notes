import { useCallback, useState } from 'react'
import { analyzeTrack } from '../api'
import { useAnalysisCache } from '../analysisCache'

/**
 * Analyse a single track. Results go into the shared cache (see analysisCache),
 * so callers read `cache.get(id)` for display; this hook only runs the fetch
 * and tracks which id is in flight.
 */
export function useAnalyze() {
  const cache = useAnalysisCache()
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const analyze = useCallback(
    (id: string) => {
      setLoadingId(id)
      setError(null)
      return analyzeTrack(id)
        .then((r) => {
          cache.set(id, r)
          return r
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : String(e))
          throw e
        })
        .finally(() => setLoadingId(null))
    },
    [cache],
  )

  const clearError = useCallback(() => setError(null), [])

  return { analyze, loadingId, error, clearError }
}
