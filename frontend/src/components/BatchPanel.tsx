import { useEffect, useMemo, useState } from 'react'
import { useBatchAnalyze } from '../hooks/useBatchAnalyze'
import { useBatchUpdate } from '../hooks/useBatchUpdate'
import type { Track } from '../types'
import { BatchConfirmDialog } from './BatchConfirmDialog'

interface Props {
  tracks: Track[]
  rekordboxRunning: boolean
  onSaved: () => void
  onClear: () => void
}

export function BatchPanel({ tracks, rekordboxRunning, onSaved, onClear }: Props) {
  const { items, running, error, progress, start, reset } = useBatchAnalyze()
  const { result, saving, error: saveError, save, reset: resetSave } = useBatchUpdate()
  const [confirming, setConfirming] = useState(false)

  const ids = useMemo(() => tracks.map((t) => t.id), [tracks])
  const idsKey = ids.join(',')

  // selection changed → drop stale analysis/results
  useEffect(() => {
    reset()
    resetSave()
    setConfirming(false)
  }, [idsKey, reset, resetSave])

  const analysed = items.size > 0 && !running
  const changes = useMemo(
    () =>
      [...items.values()].filter(
        (i) => i.ok && i.proposed_comment !== undefined && i.proposed_comment !== i.current_comment,
      ),
    [items],
  )
  const errored = [...items.values()].filter((i) => !i.ok)

  const handleConfirm = () => {
    save(changes.map((i) => ({ id: i.id, token: i.token as string })))
      .then(() => {
        setConfirming(false)
        onSaved()
      })
      .catch(() => {
        /* saveError shown in the dialog */
      })
  }

  return (
    <div className="analyze">
      <div className="analyze-head">
        <div className="analyze-title">
          <strong>{tracks.length} tracks selected</strong>{' '}
          <button className="linklike" onClick={onClear}>
            clear
          </button>
        </div>
        <button onClick={() => start(ids)} disabled={running}>
          {running ? `Analyzing ${progress.done}/${progress.total}…` : `Analyze ${tracks.length}`}
        </button>
      </div>

      {error && <p className="error">Batch analysis failed: {error}</p>}

      {items.size > 0 && (
        <table className="batch">
          <thead>
            <tr>
              <th>track</th>
              <th>token</th>
              <th>comment change</th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t) => {
              const it = items.get(t.id)
              return (
                <tr key={t.id}>
                  <td>
                    {t.title || '—'} <span className="muted">— {t.artist || '—'}</span>
                  </td>
                  {!it ? (
                    <td colSpan={2} className="muted">
                      {running ? '…' : '—'}
                    </td>
                  ) : !it.ok ? (
                    <td colSpan={2} className="error">
                      {it.error}
                    </td>
                  ) : (
                    <>
                      <td>
                        <code className="token">{it.token}</code>
                      </td>
                      <td className="comment-cell">
                        {it.proposed_comment === it.current_comment ? (
                          <span className="muted">no change</span>
                        ) : (
                          <>
                            <span className="muted">{it.current_comment || '(empty)'}</span> →{' '}
                            {it.proposed_comment}
                          </>
                        )}
                      </td>
                    </>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {analysed && !result && (
        <div className="save-row">
          <button
            onClick={() => setConfirming(true)}
            disabled={rekordboxRunning || changes.length === 0}
            title={rekordboxRunning ? 'Quit Rekordbox before saving' : undefined}
          >
            Save {changes.length} to Rekordbox
          </button>
          {errored.length > 0 && (
            <span className="warn">{errored.length} could not be analysed</span>
          )}
          {rekordboxRunning && <span className="warn">Rekordbox is running.</span>}
        </div>
      )}

      {result && (
        <p className="saved">
          Saved {result.count} comment{result.count === 1 ? '' : 's'} in one transaction. Backup:{' '}
          <code>{result.backup_path.split('/').pop()}</code>
        </p>
      )}

      {confirming && (
        <BatchConfirmDialog
          changes={changes.map((i) => ({
            id: i.id,
            label: `${i.title ?? i.id} — ${i.artist ?? ''}`,
            current: i.current_comment ?? '',
            proposed: i.proposed_comment ?? '',
          }))}
          busy={saving}
          error={saveError}
          onCancel={() => setConfirming(false)}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  )
}
