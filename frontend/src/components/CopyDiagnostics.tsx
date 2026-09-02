import { useState } from 'react'
import { fetchDiagnostics } from '../api'

type State = 'idle' | 'working' | 'copied' | 'error'

/** Footer button: copies the tail of the app log to the clipboard for support. */
export function CopyDiagnostics() {
  const [state, setState] = useState<State>('idle')

  const run = async () => {
    setState('working')
    try {
      const text = await fetchDiagnostics()
      await navigator.clipboard.writeText(text)
      setState('copied')
      setTimeout(() => setState('idle'), 2000)
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  const label =
    state === 'working'
      ? 'copying…'
      : state === 'copied'
        ? 'copied ✓'
        : state === 'error'
          ? 'copy failed'
          : 'Copy diagnostics'

  return (
    <button className="linklike" onClick={run} disabled={state === 'working'}>
      {label}
    </button>
  )
}
