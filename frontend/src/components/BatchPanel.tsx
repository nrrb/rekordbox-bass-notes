import { useEffect, useMemo, useState } from 'react'
import { itemToResponse, useAnalysisCache } from '../analysisCache'
import { useBatchAnalyze } from '../hooks/useBatchAnalyze'
import { useBatchUpdate } from '../hooks/useBatchUpdate'
import type { Track } from '../types'
import { AnalysisDetail } from './AnalysisDetail'
import { BatchConfirmDialog } from './BatchConfirmDialog'

interface Props {
  tracks: Track[]
  rekordboxRunning: boolean
  onSaved: () => void
  onClear: () => void
}

export function BatchPanel({ tracks, rekordboxRunning, onSaved, onClear }: Props) {
  const cache = useAnalysisCache()
  const { items, running, error, progress, start, seed } = useBatchAnalyze()
  const { result, saving, error: saveError, save, reset: resetSave } = useBatchUpdate()
  const [confirming, setConfirming] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const ids = useMemo(() => tracks.map((t) => t.id), [tracks])
  const idsKey = ids.join(',')

  // selection changed → show whatever's already in the cache for this set;
  // "Analyze" then only fetches the ones not yet done
  useEffect(() => {
    seed(idsKey ? idsKey.split(',') : [])
    resetSave()
    setConfirming(false)
    setExpanded(new Set())
  }, [idsKey, seed, resetSave])

  const anyResults = items.size > 0
  const analysed = anyResults && !running
  const changes = useMemo(
    () =>
      [...items.values()].filter(
        (i) => i.ok && i.proposed_comment !== undefined && i.proposed_comment !== i.current_comment,
      ),
    [items],
  )
  const errored = [...items.values()].filter((i) => !i.ok)

  const toggle = (id: string) =>
    setExpanded((s) => {
      const n = new Set(s)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })

  const handleConfirm = () => {
    save(changes.map((i) => ({ id: i.id, token: i.token as string })))
      .then((r) => {
        r.results.forEach((x) =>
          cache.patch(x.id, {
            current_comment: x.new_comment,
            proposed_comment: x.new_comment,
            existing_tokens: 1,
            merge_action: 'replaced',
          }),
        )
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
          {running
            ? `Analyzing ${progress.done}/${progress.total}…`
            : anyResults
              ? 'Re-analyze'
              : `Analyze ${tracks.length}`}
        </button>
      </div>

      {error && <p className="error">Batch analysis failed: {error}</p>}

      {anyResults && (
        <div className="batch-list">
          {tracks.map((t) => {
            const it = items.get(t.id)
            const open = expanded.has(t.id)
            return (
              <div key={t.id} className={`batch-item${open ? ' open' : ''}`}>
                <button
                  type="button"
                  className="batch-item-head"
                  disabled={!it?.ok}
                  onClick={() => it?.ok && toggle(t.id)}
                >
                  <span className="batch-item-title">
                    {t.title || '—'} <span className="muted">— {t.artist || '—'}</span>
                  </span>
                  {it?.ok && <span className="batch-item-caret">{open ? '▾' : '▸'}</span>}
                </button>

                {!it ? (
                  <div className="muted batch-item-body">{running ? 'analysing…' : '—'}</div>
                ) : !it.ok ? (
                  <div className="error batch-item-body">{it.error}</div>
                ) : (
                  <>
                    <div className="batch-item-body">
                      <code className="token">{it.token}</code>{' '}
                      {it.proposed_comment === it.current_comment ? (
                        <span className="muted">no change</span>
                      ) : (
                        <span className="batch-item-change">
                          <span className="muted">{it.current_comment || '(empty)'}</span> →{' '}
                          {it.proposed_comment}
                        </span>
                      )}
                    </div>
                    {open && (
                      <div className="batch-item-detail">
                        <AnalysisDetail data={itemToResponse(it)} />
                      </div>
                    )}
                  </>
                )}
              </div>
            )
          })}
        </div>
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
