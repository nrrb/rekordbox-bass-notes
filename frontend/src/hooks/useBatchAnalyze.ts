import { useCallback, useEffect, useRef, useState } from 'react'
import { analyzeTracksStream } from '../api'
import { itemToResponse, useAnalysisCache } from '../analysisCache'
import type { BatchAnalyzeItem } from '../types'

export function useBatchAnalyze() {
  const cache = useAnalysisCache()
  // Cache updates re-render this hook. Keep the latest API in a ref so the
  // selection helpers stay stable while a batch stream is in progress.
  const cacheRef = useRef(cache)
  useEffect(() => {
    cacheRef.current = cache
  }, [cache])
  const [items, setItems] = useState<Map<string, BatchAnalyzeItem>>(new Map())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const abortRef = useRef<AbortController | null>(null)

  /** Populate the view from the cache only — no network. Used when the
   *  selection changes so previously-analysed tracks show up straight away. */
  const seed = useCallback(
    (ids: string[]) => {
      abortRef.current?.abort()
      const m = new Map<string, BatchAnalyzeItem>()
      ids.forEach((id) => {
        const c = cacheRef.current.get(id)
        if (c) m.set(id, { ...c, id, index: 0, total: ids.length, ok: true })
      })
      setItems(m)
      setError(null)
      setRunning(false)
      setProgress({ done: m.size, total: ids.length })
    },
    [],
  )

  const start = useCallback(
    async (ids: string[]) => {
      abortRef.current?.abort()

      // seed from the cache; only stream the tracks we haven't analysed yet
      const seeded = new Map<string, BatchAnalyzeItem>()
      const uncached: string[] = []
      ids.forEach((id) => {
        const c = cacheRef.current.get(id)
        if (c) seeded.set(id, { ...c, id, index: 0, total: ids.length, ok: true })
        else uncached.push(id)
      })
      setItems(seeded)
      setError(null)
      setProgress({ done: seeded.size, total: ids.length })

      if (uncached.length === 0) {
        setRunning(false)
        return
      }

      const ac = new AbortController()
      abortRef.current = ac
      setRunning(true)
      try {
        for await (const it of analyzeTracksStream(uncached, ac.signal)) {
          if (ac.signal.aborted) break
          setItems((m) => new Map(m).set(it.id, it))
          if (it.ok) cacheRef.current.set(it.id, itemToResponse(it))
          setProgress((p) => ({ done: p.done + 1, total: ids.length }))
        }
      } catch (e: unknown) {
        if (!(e instanceof DOMException && e.name === 'AbortError')) {
          setError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        // A later selection/start owns its own running state.
        if (abortRef.current === ac) {
          abortRef.current = null
          setRunning(false)
        }
      }
    },
    [],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setItems(new Map())
    setError(null)
    setRunning(false)
    setProgress({ done: 0, total: 0 })
  }, [])

  return { items, running, error, progress, start, seed, reset }
}
