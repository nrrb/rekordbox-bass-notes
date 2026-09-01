import { useEffect, useRef } from 'react'
import { BAND_EDGES_HZ } from '../bassToken'
import { usePlayer } from '../player'
import type { Track } from '../types'

function fmt(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// Spectrum above the sub-bass split, drawn on a log frequency axis.
const SPECTRUM_BARS = 22
const SPECTRUM_MIN_HZ = BAND_EDGES_HZ[3] // 150
const SPECTRUM_MAX_HZ = 16000
const GROUP_GAP = 6 // px between the L/M/H group and the spectrum

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
    const v = (name: string, fallback: string) =>
      css.getPropertyValue(name).trim() || fallback
    const bandColors = [
      v('--band-low', '#8fe0d6'),
      v('--band-mid', '#6f8ef2'),
      v('--band-high', '#8256e0'),
    ]
    const bandLabels = ['L', 'M', 'H']
    // black or white text depending on the bar colour's perceived lightness
    const textOn = (hex: string): string => {
      const c = hex.replace('#', '')
      if (c.length < 6) return '#eef0f5'
      const r = parseInt(c.slice(0, 2), 16)
      const gc = parseInt(c.slice(2, 4), 16)
      const b = parseInt(c.slice(4, 6), 16)
      return 0.299 * r + 0.587 * gc + 0.114 * b > 140 ? '#12131a' : '#eef0f5'
    }
    const accent = v('--accent', '#6ea8fe')
    const muted = v('--border', '#2c2f3a')
    let raf = 0
    let buf = new Uint8Array(0)

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const w = (canvas.width = canvas.clientWidth || 280)
      const h = (canvas.height = canvas.clientHeight || 44)
      g.clearRect(0, 0, w, h)

      const an = analyserRef.current
      const live = !!an
      let spacing = 0
      if (an) {
        if (buf.length !== an.frequencyBinCount) {
          buf = new Uint8Array(an.frequencyBinCount)
        }
        an.getByteFrequencyData(buf)
        spacing = an.context.sampleRate / an.fftSize
      }

      // aggregate the FFT bins whose centre frequency lands in [fLo, fHi)
      const agg = (fLo: number, fHi: number, mode: 'avg' | 'max'): number => {
        if (!spacing) return 0
        let lo = Math.round(fLo / spacing)
        let hi = Math.round(fHi / spacing)
        if (lo < 1) lo = 1
        if (hi <= lo) hi = lo + 1
        let sum = 0
        let peak = 0
        let n = 0
        for (let b = lo; b < hi && b < buf.length; b++) {
          sum += buf[b]
          if (buf[b] > peak) peak = buf[b]
          n++
        }
        if (!n) return 0
        return mode === 'avg' ? sum / n : peak
      }

      const bars: { value: number; color: string; wide: boolean }[] = []
      // one dedicated, colour-coded bar per L / M / H sub-bass band
      for (let i = 0; i < 3; i++) {
        bars.push({
          value: agg(BAND_EDGES_HZ[i], BAND_EDGES_HZ[i + 1], 'avg'),
          color: bandColors[i],
          wide: true,
        })
      }
      // log-spaced spectrum for everything above 150 Hz
      const ratio = SPECTRUM_MAX_HZ / SPECTRUM_MIN_HZ
      for (let k = 0; k < SPECTRUM_BARS; k++) {
        const f0 = SPECTRUM_MIN_HZ * Math.pow(ratio, k / SPECTRUM_BARS)
        const f1 = SPECTRUM_MIN_HZ * Math.pow(ratio, (k + 1) / SPECTRUM_BARS)
        bars.push({ value: agg(f0, f1, 'max'), color: accent, wide: false })
      }

      // band bars get ~1.7× the width of a spectrum bar
      const units = 3 * 1.7 + SPECTRUM_BARS
      const unit = (w - GROUP_GAP) / units
      const bandCenters: number[] = []
      let x = 0
      bars.forEach((bar, i) => {
        if (i === 3) x += GROUP_GAP
        const bw = unit * (bar.wide ? 1.7 : 1)
        const bh = live ? Math.max(2, (bar.value / 255) * h) : 2
        const threshold = bar.wide ? 4 : 8
        g.fillStyle = live && bar.value > threshold ? bar.color : muted
        g.fillRect(x + 0.5, h - bh, Math.max(1, bw - 1), bh)
        if (bar.wide) bandCenters.push(x + bw / 2)
        x += bw
      })

      // permanent L / M / H letters on the band bars — a non-colour cue
      g.font = '600 9px system-ui, -apple-system, sans-serif'
      g.textAlign = 'center'
      g.textBaseline = 'alphabetic'
      bandCenters.forEach((cx, i) => {
        const val = bars[i].value
        const tall = live && val > 4 && (val / 255) * h > 16
        g.fillStyle = tall ? textOn(bandColors[i]) : muted
        g.fillText(bandLabels[i], cx, tall ? h - 3 : h - 6)
      })
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
      <div className="player-eq-legend">
        <span>
          <i style={{ background: 'var(--band-low, #8fe0d6)' }} /> L 20–39
        </span>
        <span>
          <i style={{ background: 'var(--band-mid, #6f8ef2)' }} /> M 39–77
        </span>
        <span>
          <i style={{ background: 'var(--band-high, #8256e0)' }} /> H 77–150 Hz
        </span>
        <span className="player-eq-legend-rest">· log spectrum →</span>
      </div>

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
