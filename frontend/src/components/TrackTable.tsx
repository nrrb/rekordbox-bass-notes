import { usePlayer } from '../player'
import type { Track } from '../types'

interface Props {
  tracks: Track[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
  onToggleAll: () => void
}

export function TrackTable({ tracks, selectedIds, onToggle, onToggleAll }: Props) {
  const player = usePlayer()

  if (tracks.length === 0) {
    return <p className="muted">No tracks match.</p>
  }

  const allSelected = tracks.every((t) => selectedIds.has(t.id))

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th className="check-col">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onToggleAll}
                title={allSelected ? 'Deselect all shown' : 'Select all shown'}
              />
            </th>
            <th className="play-col" aria-label="play" />
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th>Genre</th>
            <th>Comment</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((t) => {
            const isCurrent = player.currentId === t.id
            return (
              <tr
                key={t.id}
                className={selectedIds.has(t.id) ? 'selected' : undefined}
                onClick={() => onToggle(t.id)}
              >
                <td className="check-col">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(t.id)}
                    onChange={() => onToggle(t.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </td>
                <td className="play-col">
                  <button
                    className={`row-play${isCurrent && player.playing ? ' playing' : ''}`}
                    disabled={!t.has_file}
                    title={t.has_file ? 'Play / pause' : 'no local audio file'}
                    onClick={(e) => {
                      e.stopPropagation()
                      player.toggle(t.id)
                    }}
                  >
                    {isCurrent && player.playing ? '❚❚' : '▶'}
                  </button>
                </td>
                <td>{t.title || <span className="muted">—</span>}</td>
                <td>{t.artist || <span className="muted">—</span>}</td>
                <td>{t.album || <span className="muted">—</span>}</td>
                <td>{t.genre || <span className="muted">—</span>}</td>
                <td className="comment-cell">{t.comment || <span className="muted">—</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
