import { useEffect, useRef } from 'react'
import { usePlayer } from '../player'
import type { Track } from '../types'

function fmt(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

const BARS = 28

export function PlayerPanel({ track }: { track: Track | undefined }) {
  const player = usePlayer()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // read the analyser through a ref so a single mount-time loop always sees the
  // current node (it's null until the first play wires the Web Audio graph)
  const analyserRef = useRef<AnalyserNode | null>(null)
  analyserRef.current = player.analyser

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const g = canvas.getContext('2d')
    if (!g) return
    const css = getComputedStyle(document.documentElement)
    const accent = css.getPropertyValue('--accent').trim() || '#6ea8fe'
    const muted = css.getPropertyValue('--border').trim() || '#2c2f3a'
    let raf = 0

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const w = (canvas.width = canvas.clientWidth || 280)
      const h = (canvas.height = canvas.clientHeight || 44)
      g.clearRect(0, 0, w, h)
      const bw = w / BARS

      const an = analyserRef.current
      const levels = new Array<number>(BARS).fill(0)
      const live = !!an
      if (an) {
        const data = new Uint8Array(an.frequencyBinCount)
        an.getByteFrequencyData(data)
        const step = Math.max(1, Math.floor(data.length / BARS))
        for (let i = 0; i < BARS; i++) {
          let v = 0
          for (let j = 0; j < step; j++) v = Math.max(v, data[i * step + j] || 0)
          levels[i] = v
        }
      }

      for (let i = 0; i < BARS; i++) {
        const bh = live ? Math.max(2, (levels[i] / 255) * h) : 2
        g.fillStyle = live && levels[i] > 8 ? accent : muted
        g.fillRect(i * bw + 1, h - bh, Math.max(1, bw - 2), bh)
      }
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])

  const idle = !player.currentId

  return (
    <div className={`player${idle ? ' idle' : ''}`}>
      <div className="player-top">
        <button
          className="player-play"
          disabled={idle}
          onClick={() => !idle && player.toggle(player.currentId as string)}
          aria-label={player.playing ? 'Pause' : 'Play'}
        >
          {player.playing ? '❚❚' : '▶'}
        </button>
        <div className="player-title">
          {idle ? (
            <span className="muted">Nothing playing — press ▶ on a track</span>
          ) : track ? (
            <>
              <strong>{track.title || '—'}</strong>{' '}
              <span className="muted">— {track.artist || '—'}</span>
            </>
          ) : (
            player.currentId
          )}
        </div>
        {!idle && (
          <button className="linklike" onClick={player.stop}>
            stop
          </button>
        )}
      </div>

      <canvas ref={canvasRef} className="player-eq" />

      <div className="player-seek">
        <span className="muted">{fmt(player.currentTime)}</span>
        <input
          type="range"
          min={0}
          max={player.duration || 0}
          step={0.1}
          value={Math.min(player.currentTime, player.duration || 0)}
          disabled={idle || !player.duration}
          onChange={(e) => player.seek(Number(e.target.value))}
        />
        <span className="muted">{fmt(player.duration)}</span>
      </div>

      {player.error && <p className="error">{player.error}</p>}
    </div>
  )
}
