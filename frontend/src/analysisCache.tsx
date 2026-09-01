import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AnalyzeResponse, BatchAnalyzeItem } from './types'

/**
 * Analysis results, keyed by track id, kept for the lifetime of the current
 * library (cleared on DB switch / restore). Lets you deselect a track and come
 * back to its analysis without re-running it, and lets the batch flow skip
 * tracks already analysed singly (and vice versa).
 */
interface CacheApi {
  get: (id: string) => AnalyzeResponse | undefined
  set: (id: string, r: AnalyzeResponse) => void
  patch: (id: string, partial: Partial<AnalyzeResponse>) => void
  clear: () => void
  size: number
}

const Ctx = createContext<CacheApi | null>(null)

export function AnalysisCacheProvider({ children }: { children: ReactNode }) {
  const [map, setMap] = useState<Map<string, AnalyzeResponse>>(() => new Map())

  const set = useCallback((id: string, r: AnalyzeResponse) => {
    setMap((prev) => new Map(prev).set(id, r))
  }, [])

  const patch = useCallback((id: string, partial: Partial<AnalyzeResponse>) => {
    setMap((prev) => {
      const cur = prev.get(id)
      if (!cur) return prev
      return new Map(prev).set(id, { ...cur, ...partial })
    })
  }, [])

  const clear = useCallback(() => setMap((prev) => (prev.size ? new Map() : prev)), [])

  const get = useCallback((id: string) => map.get(id), [map])

  const api = useMemo<CacheApi>(
    () => ({ get, set, patch, clear, size: map.size }),
    [get, set, patch, clear, map.size],
  )
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>
}

export function useAnalysisCache(): CacheApi {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAnalysisCache used outside <AnalysisCacheProvider>')
  return v
}

/** Normalise a streamed batch record (ok) into the single-analyze shape. */
export function itemToResponse(it: BatchAnalyzeItem): AnalyzeResponse {
  return {
    id: it.id,
    title: it.title ?? '',
    artist: it.artist ?? '',
    audio_path: it.audio_path ?? '',
    sample_rate: it.sample_rate ?? 0,
    duration_sec: it.duration_sec ?? 0,
    bands: it.bands ?? [],
    token: it.token ?? '',
    current_comment: it.current_comment ?? '',
    proposed_comment: it.proposed_comment ?? '',
    merge_action: it.merge_action ?? 'prepended',
    existing_tokens: it.existing_tokens ?? 0,
  }
}
