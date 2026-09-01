import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { fetchHealth } from './api'
import { AnalyzePanel } from './components/AnalyzePanel'
import { TrackTable } from './components/TrackTable'
import { useTracks } from './hooks/useTracks'
import type { Health } from './types'

export default function App() {
  const { tracks, loading, error, refetch } = useTracks()
  const [health, setHealth] = useState<Health | null>(null)
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

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

  const selected = useMemo(
    () => tracks.find((t) => t.id === selectedId) ?? null,
    [tracks, selectedId],
  )

  return (
    <div className="app">
      <header>
        <h1>Rekordbox Comment Tagger</h1>
        <div className="meta">
          {health ? (
            <>
              <code>{health.db_path}</code>
              <span>{health.track_count} tracks</span>
              <span className={health.rekordbox_running ? 'warn' : 'ok'}>
                Rekordbox {health.rekordbox_running ? 'running' : 'closed'}
              </span>
            </>
          ) : (
            <span className="muted">health unavailable</span>
          )}
        </div>
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
        </span>
      </div>

      {error && <p className="error">Failed to load tracks: {error}</p>}

      {!error && (
        <TrackTable tracks={filtered} selectedId={selectedId} onSelect={setSelectedId} />
      )}

      {selected && <AnalyzePanel key={selected.id} track={selected} />}
    </div>
  )
}
