import { useState } from 'react'
import { switchDb } from '../api'
import type { Health } from '../types'

interface Props {
  health: Health
  onSwitched: (h: Health) => void
}

export function DbSwitcher({ health, onSwitched }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [path, setPath] = useState('')

  const run = (body: { target: 'live' } | { target: 'custom'; path: string }) => {
    setBusy(true)
    setError(null)
    switchDb(body)
      .then((h) => {
        setPickerOpen(false)
        setPath('')
        onSwitched(h)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  return (
    <span className="db-switch">
      {health.db_kind === 'custom' && (
        <button className="linklike" disabled={busy} onClick={() => run({ target: 'live' })}>
          use my Rekordbox library
        </button>
      )}

      {pickerOpen ? (
        <>
          <input
            className="db-path-input"
            type="text"
            placeholder="/path/to/another/master.db"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={busy}
          />
          <button
            className="linklike"
            disabled={busy || !path.trim()}
            onClick={() => run({ target: 'custom', path: path.trim() })}
          >
            {busy ? 'opening…' : 'open'}
          </button>
          <button className="linklike" disabled={busy} onClick={() => setPickerOpen(false)}>
            cancel
          </button>
        </>
      ) : (
        <button className="linklike" disabled={busy} onClick={() => setPickerOpen(true)}>
          use a different database…
        </button>
      )}

      {error && <span className="error"> — {error}</span>}
    </span>
  )
}
