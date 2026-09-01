import type { ReactNode } from 'react'

// B:l5m7h9 — any single-letter preset prefix, band letters either case
const TOKEN_RE = /[A-Za-z]:[Ll]\d[Mm]\d[Hh]\d/g

function highlight(text: string, cls: string): ReactNode {
  if (!text) return <span className="muted">(empty)</span>
  const parts: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const i = m.index ?? 0
    if (i > last) parts.push(text.slice(last, i))
    parts.push(
      <mark key={i} className={cls}>
        {m[0]}
      </mark>,
    )
    last = i + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

interface Props {
  current: string
  proposed: string
  action: 'replaced' | 'prepended'
}

export function CommentDiff({ current, proposed, action }: Props) {
  return (
    <div className="diff">
      <div className="diff-row">
        <span className="diff-label">current</span>
        <code className="diff-text">{highlight(current, 'tok-old')}</code>
      </div>
      <div className="diff-row">
        <span className="diff-label">proposed</span>
        <code className="diff-text">{highlight(proposed, 'tok-new')}</code>
      </div>
      <div className="muted diff-note">token will be {action}</div>
    </div>
  )
}
