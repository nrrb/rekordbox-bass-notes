import { useState } from 'react'
import { restoreBackup } from '../api'
import { useBackups } from '../hooks/useBackups'
import type { BackupInfo, Health } from '../types'

interface Props {
  open: boolean
  rekordboxRunning: boolean
  onRestored: (h: Health) => void
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function fmtTaken(iso: string | null): string {
  if (!iso) return 'unknown time'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export function RestorePanel({ open, rekordboxRunning, onRestored }: Props) {
  const { data, loading, error, reload } = useBackups(open)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [opError, setOpError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  if (!open) return null

  const restore = (b: BackupInfo) => {
    setBusy(true)
    setOpError(null)
    restoreBackup(b.name)
      .then((res) => {
        setConfirming(null)
        setDone(`Restored ${res.restored_from}. Previous state saved as ${res.prerestore_snapshot}.`)
        onRestored(res)
        reload()
      })
      .catch((e: unknown) => setOpError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  return (
    <div className="analyze restore-panel">
      <div className="analyze-head">
        <strong>Backups</strong>
        <button className="linklike" onClick={reload} disabled={loading}>
          {loading ? 'loading…' : 'refresh'}
        </button>
      </div>

      {error && <p className="error">Couldn't load backups: {error}</p>}
      {done && <p className="saved">{done}</p>}
      {opError && <p className="error">{opError}</p>}

      {data && (
        <>
          <p className="muted">
            {data.backups.length} backup{data.backups.length === 1 ? '' : 's'} in{' '}
            <code>{data.backup_dir}</code>. Current library: usn{' '}
            {data.live.usn ?? '—'}, {data.live.track_count ?? '—'} tracks,{' '}
            {data.live.tagged_count ?? '—'} tagged.
          </p>

          {data.backups.length === 0 && (
            <p className="muted">No backups yet — they're written before every save.</p>
          )}

          <div className="backup-list">
            {data.backups.map((b) => (
              <div key={b.name} className="backup-row">
                <div className="backup-main">
                  <code>{b.name}</code>
                  {b.is_prerestore && <span className="tag">pre-restore</span>}
                  <span className="muted">
                    {' '}
                    · {fmtTaken(b.taken)} · {fmtSize(b.size)}
                  </span>
                </div>
                {b.error ? (
                  <div className="error">couldn't read: {b.error}</div>
                ) : (
                  <div className="muted backup-stats">
                    usn {b.usn ?? '—'} · {b.track_count ?? '—'} tracks ·{' '}
                    {b.tagged_count ?? '—'} tagged
                    {b.recent.length > 0 && (
                      <> · last edit {b.recent[0].updated_at.slice(0, 19)} “{b.recent[0].title}”</>
                    )}
                  </div>
                )}

                {confirming === b.name ? (
                  <div className="backup-confirm">
                    <span className="warn">
                      Overwrite your current library with this backup?
                    </span>
                    <button disabled={busy} onClick={() => restore(b)}>
                      {busy ? 'restoring…' : 'Confirm restore'}
                    </button>
                    <button className="secondary" disabled={busy} onClick={() => setConfirming(null)}>
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    className="linklike"
                    disabled={rekordboxRunning}
                    title={rekordboxRunning ? 'Quit Rekordbox first' : undefined}
                    onClick={() => {
                      setConfirming(b.name)
                      setDone(null)
                      setOpError(null)
                    }}
                  >
                    restore this
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
