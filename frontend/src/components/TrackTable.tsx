import type { Track } from '../types'

interface Props {
  tracks: Track[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function TrackTable({ tracks, selectedId, onSelect }: Props) {
  if (tracks.length === 0) {
    return <p className="muted">No tracks match.</p>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th>Genre</th>
            <th>Comment</th>
            <th title="Local audio file present (analysable)">File</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((t) => (
            <tr
              key={t.id}
              className={t.id === selectedId ? 'selected' : undefined}
              onClick={() => onSelect(t.id)}
            >
              <td>{t.title || <span className="muted">—</span>}</td>
              <td>{t.artist || <span className="muted">—</span>}</td>
              <td>{t.album || <span className="muted">—</span>}</td>
              <td>{t.genre || <span className="muted">—</span>}</td>
              <td className="comment-cell">{t.comment || <span className="muted">—</span>}</td>
              <td className="center">{t.has_file ? '●' : <span className="muted">○</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
