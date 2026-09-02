import { useState } from 'react'
import { pickFile } from '../api'

interface Props {
  onPicked: (path: string) => void
  className?: string
  label?: string
}

/**
 * Opens the OS "choose a file" dialog in the packaged app. Renders nothing when
 * there's no native shell (dev / plain browser), so the text path field stays
 * the only way in.
 */
export function BrowseButton({ onPicked, className = 'linklike', label = 'Browse…' }: Props) {
  const [supported, setSupported] = useState(true)
  const [busy, setBusy] = useState(false)

  if (!supported) return null

  const run = () => {
    setBusy(true)
    pickFile()
      .then((path) => {
        if (path === undefined) setSupported(false)
        else if (path) onPicked(path)
      })
      .catch(() => setSupported(false))
      .finally(() => setBusy(false))
  }

  return (
    <button type="button" className={className} disabled={busy} onClick={run}>
      {busy ? 'choosing…' : label}
    </button>
  )
}
