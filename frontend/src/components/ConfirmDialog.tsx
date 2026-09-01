interface Props {
  trackLabel: string
  oldComment: string
  newComment: string
  busy: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
}

export function ConfirmDialog({
  trackLabel,
  oldComment,
  newComment,
  busy,
  error,
  onCancel,
  onConfirm,
}: Props) {
  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Update comment?</h2>
        <p className="modal-track">{trackLabel}</p>

        <div className="modal-row">
          <span className="diff-label">old</span>
          <code className="diff-text">{oldComment || <span className="muted">(empty)</span>}</code>
        </div>
        <div className="modal-row">
          <span className="diff-label">new</span>
          <code className="diff-text">{newComment}</code>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="modal-actions">
          <button className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button onClick={onConfirm} disabled={busy}>
            {busy ? 'Saving…' : 'Confirm & Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
