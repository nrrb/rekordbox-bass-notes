import { useEffect, useState } from 'react'
import { useAnalyze } from '../hooks/useAnalyze'
import { useUpdateComment } from '../hooks/useUpdateComment'
import type { Track } from '../types'
import { CommentDiff } from './CommentDiff'
import { ConfirmDialog } from './ConfirmDialog'

interface Props {
  track: Track
  rekordboxRunning: boolean
  /** Called after a successful save so the parent can refresh the track list. */
  onSaved: () => void
}

export function AnalyzePanel({ track, rekordboxRunning, onSaved }: Props) {
  const { data, loading, error, analyze, reset } = useAnalyze()
  const { result, saving, error: saveError, save, reset: resetSave } = useUpdateComment()
  const [confirming, setConfirming] = useState(false)

  // clear stale results when the selected track changes
  useEffect(() => {
    reset()
    resetSave()
    setConfirming(false)
  }, [track.id, reset, resetSave])

  const handleConfirm = () => {
    if (!data) return
    save(track.id, data.token)
      .then(() => {
        setConfirming(false)
        onSaved()
      })
      .catch(() => {
        /* error is surfaced in the dialog via saveError; keep it open */
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
          {loading ? 'Analyzing…' : 'Analyze audio'}
        </button>
      </div>

      {!track.has_file && (
        <p className="muted">No local audio file — analysis unavailable for this track.</p>
      )}
      {error && <p className="error">Analysis failed: {error}</p>}

      {data && (
        <>
          <table className="bands">
            <thead>
              <tr>
                <th>band</th>
                <th>range</th>
                <th>RMS</th>
                <th>dBFS</th>
                <th>digit</th>
              </tr>
            </thead>
            <tbody>
              {data.bands.map((b) => (
                <tr key={b.band}>
                  <td>{b.band}</td>
                  <td>
                    {b.hz_low.toFixed(0)}–{b.hz_high.toFixed(0)} Hz
                  </td>
                  <td>{b.rms.toFixed(5)}</td>
                  <td>{b.dbfs.toFixed(1)}</td>
                  <td className="digit">{b.digit}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="token-line">
            token <code className="token">{data.token}</code>
            <span
              className="muted"
              title={`Audio is downsampled to ${data.sample_rate} Hz for analysis (only 20–150 Hz matters)`}
            >
              {' '}
              · {data.duration_sec.toFixed(0)}s track · analysed at {data.sample_rate} Hz
            </span>
          </div>

          <CommentDiff
            current={data.current_comment}
            proposed={data.proposed_comment}
            action={data.merge_action}
          />

          {data.existing_tokens > 1 && (
            <p className="warn">
              {data.existing_tokens} existing tokens found — all removed, replaced by one.
            </p>
          )}

          {result ? (
            <p className="saved">
              Saved. <code>{result.old_comment || '(empty)'}</code> →{' '}
              <code>{result.new_comment}</code>
            </p>
          ) : (
            <div className="save-row">
              <button
                onClick={() => setConfirming(true)}
                disabled={rekordboxRunning}
                title={rekordboxRunning ? 'Quit Rekordbox before saving' : undefined}
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
