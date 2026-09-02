import { openExternal } from '../api'
import type { UpdateInfo } from '../types'

interface Props {
  info: UpdateInfo | null
  onDismiss: () => void
}

/** "vX.Y.Z is available" — shown once per new release until dismissed. */
export function UpdateBanner({ info, onDismiss }: Props) {
  if (!info || !info.supported || !info.update_available || !info.latest) return null

  const open = () => {
    if (!info.url) return
    openExternal(info.url).catch(() => window.open(info.url as string, '_blank', 'noreferrer'))
  }

  return (
    <div className="update-banner" role="status">
      <span>
        <strong>{info.latest} is available.</strong> You're running v{info.current}.
      </span>
      <span className="update-banner-actions">
        {info.url && (
          <button className="linklike" onClick={open}>
            Download
          </button>
        )}
        <button className="linklike" onClick={onDismiss}>
          dismiss
        </button>
      </span>
    </div>
  )
}
