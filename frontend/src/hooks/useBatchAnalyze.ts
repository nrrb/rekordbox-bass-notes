import { useCallback, useRef, useState } from 'react'
import { analyzeTracksStream } from '../api'
import type { BatchAnalyzeItem } from '../types'

export function useBatchAnalyze() {
  const [items, setItems] = useState<Map<string, BatchAnalyzeItem>>(new Map())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const abortRef = useRef<AbortController | null>(null)

  const start = useCallback(async (ids: string[]) => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    setRunning(true)
    setError(null)
    setItems(new Map())
    setProgress({ done: 0, total: ids.length })
    try {
      for await (const it of analyzeTracksStream(ids, ac.signal)) {
        setItems((m) => new Map(m).set(it.id, it))
        setProgress({ done: it.index, total: it.total })
      }
    } catch (e: unknown) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) {
        setError(e instanceof Error ? e.message : String(e))
      }
    } finally {
      setRunning(false)
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setItems(new Map())
    setError(null)
    setRunning(false)
    setProgress({ done: 0, total: 0 })
  }, [])

  return { items, running, error, progress, start, reset }
}
