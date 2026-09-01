import { useCallback, useState } from 'react'
import { updateComments } from '../api'
import type { BatchCommentResult } from '../types'

export function useBatchUpdate() {
  const [result, setResult] = useState<BatchCommentResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = useCallback((items: { id: string; token: string }[]) => {
    setSaving(true)
    setError(null)
    return updateComments(items)
      .then((r) => {
        setResult(r)
        return r
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
        throw e
      })
      .finally(() => setSaving(false))
  }, [])

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
    setSaving(false)
  }, [])

  return { result, saving, error, save, reset }
}
