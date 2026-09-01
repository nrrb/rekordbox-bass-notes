interface Change {
  id: string
  label: string
  current: string
  proposed: string
}

interface Props {
  changes: Change[]
  busy: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
}

export function BatchConfirmDialog({ changes, busy, error, onCancel, onConfirm }: Props) {
  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onCancel}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h2>Write {changes.length} comment{changes.length === 1 ? '' : 's'}?</h2>
        <p className="modal-track">
          One transaction, one backup. Rekordbox must stay closed.
        </p>

        <div className="batch-confirm-list">
          {changes.map((c) => (
            <div key={c.id} className="batch-confirm-row">
              <div className="batch-confirm-label">{c.label}</div>
              <code className="diff-text">
                <span className="muted">{c.current || '(empty)'}</span>
                {'  →  '}
                {c.proposed}
              </code>
            </div>
          ))}
        </div>

        {error && <p className="error">{error}</p>}

        <div className="modal-actions">
          <button className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button onClick={onConfirm} disabled={busy}>
            {busy ? 'Saving…' : `Confirm & Save ${changes.length}`}
          </button>
        </div>
      </div>
    </div>
  )
}
