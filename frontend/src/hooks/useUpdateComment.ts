import { useCallback, useState } from 'react'
import { updateComment } from '../api'
import type { CommentUpdateResult } from '../types'

export function useUpdateComment() {
  const [result, setResult] = useState<CommentUpdateResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = useCallback((id: string, token: string) => {
    setSaving(true)
    setError(null)
    return updateComment(id, { token })
      .then((r) => {
        setResult(r)
        return r
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
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
