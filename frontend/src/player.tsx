import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'

interface PlayerApi {
  currentId: string | null
  playing: boolean
  currentTime: number
  duration: number
  error: string | null
  /** Play `id`; if it's already current, toggle play/pause. */
  toggle: (id: string) => void
  seek: (seconds: number) => void
  stop: () => void
  analyser: AnalyserNode | null
}

const Ctx = createContext<PlayerApi | null>(null)

function audioUrl(id: string) {
  return `/api/tracks/${encodeURIComponent(id)}/audio`
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)

  const [currentId, setCurrentId] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)

  // Wire the Web Audio graph once, on the first user-initiated play.
  const ensureGraph = useCallback(() => {
    if (ctxRef.current || !audioRef.current) return
    const AC: typeof AudioContext =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ac = new AC()
    const src = ac.createMediaElementSource(audioRef.current)
    const an = ac.createAnalyser()
    an.fftSize = 128
    an.smoothingTimeConstant = 0.8
    src.connect(an)
    an.connect(ac.destination)
    ctxRef.current = ac
    setAnalyser(an)
  }, [])

  const play = useCallback((a: HTMLAudioElement) => {
    ensureGraph()
    ctxRef.current?.resume().catch(() => {})
    a.play().catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [ensureGraph])

  const toggle = useCallback(
    (id: string) => {
      const a = audioRef.current
      if (!a) return
      setError(null)
      if (id === currentId) {
        a.paused ? play(a) : a.pause()
        return
      }
      setCurrentId(id)
      setCurrentTime(0)
      setDuration(0)
      a.src = audioUrl(id)
      play(a)
    },
    [currentId, play],
  )

  const seek = useCallback((seconds: number) => {
    if (audioRef.current) audioRef.current.currentTime = seconds
  }, [])

  const stop = useCallback(() => {
    const a = audioRef.current
    if (a) {
      a.pause()
      a.removeAttribute('src')
      a.load()
    }
    setCurrentId(null)
    setPlaying(false)
    setCurrentTime(0)
    setDuration(0)
  }, [])

  const api = useMemo<PlayerApi>(
    () => ({ currentId, playing, currentTime, duration, error, toggle, seek, stop, analyser }),
    [currentId, playing, currentTime, duration, error, toggle, seek, stop, analyser],
  )

  return (
    <Ctx.Provider value={api}>
      {children}
      <audio
        ref={audioRef}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
        onDurationChange={(e) => setDuration(e.currentTarget.duration || 0)}
        onError={() =>
          setError("Couldn't play this file — the browser may not support its format.")
        }
      />
    </Ctx.Provider>
  )
}

export function usePlayer(): PlayerApi {
  const v = useContext(Ctx)
  if (!v) throw new Error('usePlayer used outside <PlayerProvider>')
  return v
}
