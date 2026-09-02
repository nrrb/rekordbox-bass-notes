import { useCallback, useMemo, useState } from 'react'
import './App.css'
import { useAnalysisCache } from './analysisCache'
import { AnalyzePanel } from './components/AnalyzePanel'
import { BatchPanel } from './components/BatchPanel'
import { CopyDiagnostics } from './components/CopyDiagnostics'
import { DbSwitcher } from './components/DbSwitcher'
import { NoLibrary } from './components/NoLibrary'
import { PlayerPanel } from './components/PlayerPanel'
import { RekordboxBanner } from './components/RekordboxBanner'
import { RestorePanel } from './components/RestorePanel'
import { TrackTable } from './components/TrackTable'
import { UpdateBanner } from './components/UpdateBanner'
import { usePlayer } from './player'
import { useHealth } from './hooks/useHealth'
import { useTracks } from './hooks/useTracks'
import { useUpdateCheck } from './hooks/useUpdateCheck'
import type { Health } from './types'

export default function App() {
  const cache = useAnalysisCache()
  const player = usePlayer()
  const { health, reachable, reload: reloadHealth, setHealth } = useHealth()
  const { info: updateInfo, dismiss: dismissUpdate } = useUpdateCheck()
  const { tracks, loading, error, refetch } = useTracks()
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showBackups, setShowBackups] = useState(false)
  const [rechecking, setRechecking] = useState(false)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return tracks
    return tracks.filter((t) =>
      `${t.title} ${t.artist} ${t.album} ${t.genre} ${t.comment}`.toLowerCase().includes(q),
    )
  }, [tracks, search])

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      const shownIds = filtered.map((t) => t.id)
      const allSelected = shownIds.every((id) => prev.has(id))
      const next = new Set(prev)
      shownIds.forEach((id) => (allSelected ? next.delete(id) : next.add(id)))
      return next
    })
  }, [filtered])

  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  const selectedTracks = useMemo(
    () => tracks.filter((t) => selectedIds.has(t.id)),
    [tracks, selectedIds],
  )

  const rekordboxRunning = health?.rekordbox_running ?? false

  // Health object pushed from an endpoint (switch / restore) → the library
  // changed, so wipe the analysis cache and reload.
  const onHealthChanged = useCallback(
    (h: Health) => {
      setHealth(h)
      cache.clear()
      clearSelection()
      refetch()
    },
    [setHealth, cache, clearSelection, refetch],
  )

  const recheck = useCallback(() => {
    setRechecking(true)
    reloadHealth().finally(() => setRechecking(false))
  }, [reloadHealth])

  return (
    <div className="app">
      <header>
        <h1>rekordbox bass notes</h1>
        {!health ? (
          <div className="meta">
            <span className="muted">
              {reachable ? 'connecting…' : 'backend unreachable — is it running?'}
            </span>
          </div>
        ) : health.db_kind === 'none' ? (
          <div className="meta">
            <span className="db-badge db-none">NO DATABASE</span>
          </div>
        ) : (
          <>
            <div className="meta">
              <span
                className={`db-badge db-${health.db_kind}`}
                title={
                  health.db_kind === 'live'
                    ? 'Your Rekordbox library (auto-located)'
                    : 'A database you opened manually — not your main library'
                }
              >
                {health.db_kind === 'live' ? 'MY LIBRARY' : 'CUSTOM DATABASE'}
              </span>
              <code>{health.db_path}</code>
              <span title={`${health.track_count} total in the library`}>
                {health.local_track_count} tracks with files
              </span>
              <span className={health.rekordbox_running ? 'warn' : 'ok'}>
                Rekordbox {health.rekordbox_running ? 'running' : 'closed'}
              </span>
              <DbSwitcher health={health} onSwitched={onHealthChanged} />
            </div>
            {health.db_kind !== 'live' && health.detected_library_path && (
              <div className="meta detected">
                detected library: <code>{health.detected_library_path}</code>
              </div>
            )}
            {health.rekordbox_agent_running && !health.rekordbox_running && (
              <div className="meta detected">
                Rekordbox cloud sync agent is running — pause sync before saving so
                it doesn't overwrite your edits.
              </div>
            )}
          </>
        )}
      </header>

      <UpdateBanner info={updateInfo} onDismiss={dismissUpdate} />

      {rekordboxRunning && <RekordboxBanner onRecheck={recheck} busy={rechecking} />}

      {health && health.db_kind === 'none' ? (
        <NoLibrary health={health} onOpened={onHealthChanged} onRetry={recheck} />
      ) : (
        <>
          <div className="toolbar">
            <input
              type="search"
              placeholder="Filter by title, artist, album, genre, comment…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button onClick={refetch} disabled={loading}>
              {loading ? 'Loading…' : 'Reload'}
            </button>
            <button className="secondary" onClick={() => setShowBackups((s) => !s)}>
              {showBackups ? 'Hide backups' : 'Backups'}
            </button>
            <span className="muted">
              {filtered.length} shown{search ? ` / ${tracks.length} loaded` : ''}
              {selectedIds.size > 0 && ` · ${selectedIds.size} selected`}
            </span>
          </div>

          <RestorePanel
            open={showBackups}
            rekordboxRunning={rekordboxRunning}
            onRestored={onHealthChanged}
          />

          {error && <p className="error">Failed to load tracks: {error}</p>}

          {!error && (
            <div className="workspace">
              <div className="workspace-list">
                <TrackTable
                  tracks={filtered}
                  selectedIds={selectedIds}
                  onToggle={toggle}
                  onToggleAll={toggleAll}
                />
              </div>

              <aside className="workspace-detail">
                <PlayerPanel track={tracks.find((t) => t.id === player.currentId)} />

                {selectedTracks.length === 0 && (
                  <p className="detail-empty muted">
                    Select a track to analyse its low end. Pick two or more for a
                    batch.
                  </p>
                )}

                {selectedTracks.length === 1 && (
                  <AnalyzePanel
                    key={selectedTracks[0].id}
                    track={selectedTracks[0]}
                    rekordboxRunning={rekordboxRunning}
                    onSaved={refetch}
                  />
                )}

                {selectedTracks.length >= 2 && (
                  <BatchPanel
                    tracks={selectedTracks}
                    rekordboxRunning={rekordboxRunning}
                    onSaved={refetch}
                    onClear={clearSelection}
                  />
                )}
              </aside>
            </div>
          )}
        </>
      )}

      <footer className="app-footer">
        <span>rekordbox bass notes{health ? ` v${health.version}` : ''}</span>
        <CopyDiagnostics />
      </footer>
    </div>
  )
}
