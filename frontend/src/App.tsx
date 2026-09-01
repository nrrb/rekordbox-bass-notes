import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import { fetchHealth } from './api'
import { AnalyzePanel } from './components/AnalyzePanel'
import { BatchPanel } from './components/BatchPanel'
import { DbSwitcher } from './components/DbSwitcher'
import { TrackTable } from './components/TrackTable'
import { useTracks } from './hooks/useTracks'
import type { Health } from './types'

export default function App() {
  const { tracks, loading, error, refetch } = useTracks()
  const [health, setHealth] = useState<Health | null>(null)
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

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

  return (
    <div className="app">
      <header>
        <h1>Rekordbox Comment Tagger</h1>
        {health ? (
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
              <DbSwitcher
                health={health}
                onSwitched={(h) => {
                  setHealth(h)
                  clearSelection()
                  refetch()
                }}
              />
            </div>
            {health.db_kind !== 'live' && health.detected_library_path && (
              <div className="meta detected">
                detected library: <code>{health.detected_library_path}</code>
              </div>
            )}
          </>
        ) : (
          <div className="meta">
            <span className="muted">health unavailable</span>
          </div>
        )}
      </header>

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
        <span className="muted">
          {filtered.length} shown{search ? ` / ${tracks.length} loaded` : ''}
          {selectedIds.size > 0 && ` · ${selectedIds.size} selected`}
        </span>
      </div>

      {error && <p className="error">Failed to load tracks: {error}</p>}

      {!error && (
        <TrackTable
          tracks={filtered}
          selectedIds={selectedIds}
          onToggle={toggle}
          onToggleAll={toggleAll}
        />
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
    </div>
  )
}
