import { useEffect, useState } from 'react'
import { useAnalysisCache } from '../analysisCache'
import { useAnalyze } from '../hooks/useAnalyze'
import { useUpdateComment } from '../hooks/useUpdateComment'
import type { Track } from '../types'
import { AnalysisDetail } from './AnalysisDetail'
import { ConfirmDialog } from './ConfirmDialog'

interface Props {
  track: Track
  rekordboxRunning: boolean
  /** Called after a successful save so the parent can refresh the track list. */
  onSaved: () => void
}

export function AnalyzePanel({ track, rekordboxRunning, onSaved }: Props) {
  const cache = useAnalysisCache()
  const { analyze, loadingId, error, clearError } = useAnalyze()
  const { result, saving, error: saveError, save, reset: resetSave } = useUpdateComment()
  const [confirming, setConfirming] = useState(false)

  const data = cache.get(track.id) // survives deselect/reselect for this library
  const loading = loadingId === track.id
  const dirty = data && data.current_comment !== data.proposed_comment

  useEffect(() => {
    resetSave()
    clearError()
    setConfirming(false)
  }, [track.id, resetSave, clearError])

  const handleConfirm = () => {
    if (!data) return
    save(track.id, data.token)
      .then((r) => {
        // keep the cached entry consistent with what's now on disk
        cache.patch(track.id, {
          current_comment: r.new_comment,
          proposed_comment: r.new_comment,
          existing_tokens: 1,
          merge_action: 'replaced',
        })
        setConfirming(false)
        onSaved()
      })
      .catch(() => {
        /* saveError is surfaced in the dialog */
      })
  }

  return (
    <div className="analyze">
      <div className="analyze-head">
        <div className="analyze-title">
          <strong>{track.title || '—'}</strong>
          <span className="muted"> — {track.artist || '—'}</span>
        </div>
        <button
          onClick={() => analyze(track.id)}
          disabled={loading || !track.has_file}
          title={track.has_file ? undefined : 'no local audio file'}
        >
          {loading ? 'Analyzing…' : data ? 'Re-analyze' : 'Analyze audio'}
        </button>
      </div>

      {!track.has_file && (
        <p className="muted">No local audio file — analysis unavailable for this track.</p>
      )}
      {error && <p className="error">Analysis failed: {error}</p>}
      {!data && !loading && track.has_file && (
        <p className="muted">Not analysed yet.</p>
      )}

      {data && (
        <>
          <AnalysisDetail data={data} />

          {result && (
            <p className="saved">
              Saved. <code>{result.old_comment || '(empty)'}</code> →{' '}
              <code>{result.new_comment}</code>
            </p>
          )}

          {!result && (
            <div className="save-row">
              <button
                onClick={() => setConfirming(true)}
                disabled={rekordboxRunning || !dirty}
                title={
                  rekordboxRunning
                    ? 'Quit Rekordbox before saving'
                    : !dirty
                      ? 'Comment already has this token'
                      : undefined
                }
              >
                Save to Rekordbox
              </button>
              {rekordboxRunning && (
                <span className="warn">Rekordbox is running — quit it to save.</span>
              )}
            </div>
          )}
        </>
      )}

      {confirming && data && (
        <ConfirmDialog
          trackLabel={`${track.title || '—'} — ${track.artist || '—'}`}
          oldComment={data.current_comment}
          newComment={data.proposed_comment}
          busy={saving}
          error={saveError}
          onCancel={() => setConfirming(false)}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  )
}
