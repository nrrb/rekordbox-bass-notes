import { useCallback, useEffect, useState } from 'react'
import { fetchTracks } from '../api'
import type { Track } from '../types'

interface State {
  tracks: Track[]
  loading: boolean
  error: string | null
}

/**
 * Loads the full track list once (server caps it). Filtering is done
 * client-side by the caller; `search` here is only used for an optional
 * initial server-side narrowing and a manual refetch.
 */
export function useTracks(): State & { refetch: () => void } {
  const [state, setState] = useState<State>({ tracks: [], loading: true, error: null })

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }))
    fetchTracks()
      .then((tracks) => setState({ tracks, loading: false, error: null }))
      .catch((e: unknown) =>
        setState({ tracks: [], loading: false, error: e instanceof Error ? e.message : String(e) }),
      )
  }, [])

  useEffect(load, [load])

  return { ...state, refetch: load }
}
