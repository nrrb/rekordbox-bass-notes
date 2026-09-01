import type {
  AnalyzeResponse,
  BatchAnalyzeItem,
  BatchCommentResult,
  CommentUpdateResult,
  Health,
  Track,
} from './types'

async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export function fetchHealth(): Promise<Health> {
  return getJSON<Health>('/api/health')
}

/** Reopen the backend against a different master.db at runtime. Returns fresh health. */
export function switchDb(target: 'live' | 'sample'): Promise<Health> {
  return getJSON<Health>('/api/db/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target }),
  })
}

export function fetchTracks(params: { search?: string; limit?: number } = {}): Promise<Track[]> {
  const qs = new URLSearchParams()
  if (params.search) qs.set('search', params.search)
  if (params.limit != null) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs}` : ''
  return getJSON<Track[]>(`/api/tracks${suffix}`)
}

export function fetchTrack(id: string): Promise<Track> {
  return getJSON<Track>(`/api/tracks/${encodeURIComponent(id)}`)
}

export function analyzeTrack(id: string): Promise<AnalyzeResponse> {
  return getJSON<AnalyzeResponse>(`/api/tracks/${encodeURIComponent(id)}/analyze`, {
    method: 'POST',
  })
}

/** Writes the comment. Pass exactly one of `token` (merge) or `comment` (replace). */
export function updateComment(
  id: string,
  body: { token: string } | { comment: string },
): Promise<CommentUpdateResult> {
  return getJSON<CommentUpdateResult>(`/api/tracks/${encodeURIComponent(id)}/comment`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** Batch analyse; yields one record per track as the NDJSON stream arrives. */
export async function* analyzeTracksStream(
  ids: string[],
  signal?: AbortSignal,
): AsyncGenerator<BatchAnalyzeItem> {
  const res = await fetch('/api/tracks/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let nl: number
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (line) yield JSON.parse(line) as BatchAnalyzeItem
    }
  }
  const tail = buf.trim()
  if (tail) yield JSON.parse(tail) as BatchAnalyzeItem
}

/** Writes many comments in one atomic transaction. */
export function updateComments(
  items: ({ id: string; token: string } | { id: string; comment: string })[],
): Promise<BatchCommentResult> {
  return getJSON<BatchCommentResult>('/api/tracks/comments', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
}
