import { useMemo, useState } from 'react'
import { parseBassToken } from '../bassToken'
import { usePlayer } from '../player'
import type { Track } from '../types'

interface Props {
  tracks: Track[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
  onToggleAll: () => void
}

type SortKey = 'title' | 'artist' | 'genre' | 'comment' | 'l' | 'm' | 'h'
type SortDir = 'asc' | 'desc'

interface Row {
  track: Track
  l: number | null
  m: number | null
  h: number | null
}

const NUM_KEYS = new Set<SortKey>(['l', 'm', 'h'])

type Sort = { key: SortKey; dir: SortDir } | null

function SortHeader({
  k,
  label,
  cls,
  sort,
  onSort,
}: {
  k: SortKey
  label: string
  cls?: string
  sort: Sort
  onSort: (k: SortKey) => void
}) {
  const active = sort?.key === k
  return (
    <th
      className={`sortable${cls ? ` ${cls}` : ''}${active ? ' sorted' : ''}`}
      onClick={() => onSort(k)}
      title={`Sort by ${label}`}
    >
      {label}
      <span className="sort-arrow">{active ? (sort!.dir === 'asc' ? ' ▲' : ' ▼') : ''}</span>
    </th>
  )
}

function compare(a: Row, b: Row, key: SortKey, dir: SortDir): number {
  const sign = dir === 'asc' ? 1 : -1
  if (NUM_KEYS.has(key)) {
    const av = a[key as 'l' | 'm' | 'h']
    const bv = b[key as 'l' | 'm' | 'h']
    // rows without a token always sort to the bottom, regardless of direction
    if (av === null && bv === null) return 0
    if (av === null) return 1
    if (bv === null) return -1
    return (av - bv) * sign
  }
  const tk = key as 'title' | 'artist' | 'genre' | 'comment'
  const av = (a.track[tk] || '').toLowerCase()
  const bv = (b.track[tk] || '').toLowerCase()
  if (!av && !bv) return 0
  if (!av) return 1
  if (!bv) return -1
  return av.localeCompare(bv) * sign
}

export function TrackTable({ tracks, selectedIds, onToggle, onToggleAll }: Props) {
  const player = usePlayer()
  const [sort, setSort] = useState<Sort>(null)

  const rows = useMemo<Row[]>(
    () =>
      tracks.map((track) => {
        const b = parseBassToken(track.comment)
        return { track, l: b?.l ?? null, m: b?.m ?? null, h: b?.h ?? null }
      }),
    [tracks],
  )

  const sorted = useMemo<Row[]>(() => {
    if (!sort) return rows
    return [...rows].sort((a, b) => compare(a, b, sort.key, sort.dir))
  }, [rows, sort])

  if (tracks.length === 0) {
    return <p className="muted">No tracks match.</p>
  }

  const allSelected = tracks.every((t) => selectedIds.has(t.id))

  const clickHeader = (key: SortKey) => {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null // third click clears the sort
    })
  }

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
            <SortHeader k="title" label="Title" sort={sort} onSort={clickHeader} />
            <SortHeader k="artist" label="Artist" sort={sort} onSort={clickHeader} />
            <SortHeader k="genre" label="Genre" sort={sort} onSort={clickHeader} />
            <SortHeader k="l" label="l" cls="num-col" sort={sort} onSort={clickHeader} />
            <SortHeader k="m" label="m" cls="num-col" sort={sort} onSort={clickHeader} />
            <SortHeader k="h" label="h" cls="num-col" sort={sort} onSort={clickHeader} />
            <SortHeader k="comment" label="Comment" sort={sort} onSort={clickHeader} />
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ track: t, l, m, h }) => {
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
                <td>{t.genre || <span className="muted">—</span>}</td>
                <td className="num-col">{l ?? <span className="muted">—</span>}</td>
                <td className="num-col">{m ?? <span className="muted">—</span>}</td>
                <td className="num-col">{h ?? <span className="muted">—</span>}</td>
                <td className="comment-cell">{t.comment || <span className="muted">—</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
