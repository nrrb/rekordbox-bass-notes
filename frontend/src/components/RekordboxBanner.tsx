interface Props {
  onRecheck: () => void
  busy: boolean
}

/** Persistent banner shown while Rekordbox is running (writes are blocked). */
export function RekordboxBanner({ onRecheck, busy }: Props) {
  return (
    <div className="rb-banner" role="status">
      <span>
        <strong>Rekordbox is open.</strong> Analysis works, but saving is blocked
        until you quit it.
      </span>
      <button onClick={onRecheck} disabled={busy}>
        {busy ? 'checking…' : "I've quit it — re-check"}
      </button>
    </div>
  )
}
