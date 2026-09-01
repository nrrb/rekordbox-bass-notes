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
  const [confirmLive, setConfirmLive] = useState(false)

  const go = (target: 'live' | 'sample') => {
    setBusy(true)
    setError(null)
    switchDb(target)
      .then((h) => {
        setConfirmLive(false)
        onSwitched(h)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const canGoLive = health.db_kind !== 'live' && !!health.detected_library_path

  return (
    <span className="db-switch">
      {health.db_kind === 'live' && (
        <button className="linklike" disabled={busy} onClick={() => go('sample')}>
          {busy ? 'switching…' : 'switch to sample copy'}
        </button>
      )}

      {health.db_kind !== 'live' &&
        (confirmLive ? (
          <>
            <span className="warn">Point saves at your real library?</span>{' '}
            <button className="linklike" disabled={busy} onClick={() => go('live')}>
              {busy ? 'switching…' : 'yes, use live library'}
            </button>{' '}
            <button className="linklike" disabled={busy} onClick={() => setConfirmLive(false)}>
              cancel
            </button>
          </>
        ) : (
          <>
            {canGoLive && (
              <button className="linklike" disabled={busy} onClick={() => setConfirmLive(true)}>
                switch to live library
              </button>
            )}
            {health.db_kind === 'custom' && (
              <button className="linklike" disabled={busy} onClick={() => go('sample')}>
                {canGoLive ? ' · use sample copy' : 'use sample copy'}
              </button>
            )}
          </>
        ))}

      {error && <span className="error"> — {error}</span>}
    </span>
  )
}
