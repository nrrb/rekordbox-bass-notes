import { useState } from 'react'
import { switchDb } from '../api'
import type { Health } from '../types'

interface Props {
  health: Health
  onOpened: (h: Health) => void
  onRetry: () => void
}

export function NoLibrary({ health, onOpened, onRetry }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [path, setPath] = useState('')

  const open = (body: { target: 'live' } | { target: 'custom'; path: string }) => {
    setBusy(true)
    setError(null)
    switchDb(body)
      .then(onOpened)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  return (
    <div className="no-library">
      <h2>No Rekordbox library open</h2>
      <p className="muted">
        The app couldn't open a Rekordbox database. Point it at your{' '}
        <code>master.db</code> — usually in{' '}
        <code>~/Library/Pioneer/rekordbox/</code> or <code>…/rekordbox7/</code>.
      </p>

      {health.detected_library_path && (
        <div className="no-library-row">
          <span>
            Found one at <code>{health.detected_library_path}</code>
          </span>
          <button disabled={busy} onClick={() => open({ target: 'live' })}>
            {busy ? 'opening…' : 'Open it'}
          </button>
        </div>
      )}

      <div className="no-library-row">
        <input
          type="text"
          className="db-path-input"
          placeholder="/path/to/master.db"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          disabled={busy}
        />
        <button
          disabled={busy || !path.trim()}
          onClick={() => open({ target: 'custom', path: path.trim() })}
        >
          Open
        </button>
      </div>

      <div className="no-library-row">
        <button className="secondary" disabled={busy} onClick={onRetry}>
          Retry auto-detect
        </button>
      </div>

      {error && <p className="error">{error}</p>}
    </div>
  )
}
