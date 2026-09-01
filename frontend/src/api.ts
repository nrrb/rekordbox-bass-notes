import type { Health, Track } from './types'

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
