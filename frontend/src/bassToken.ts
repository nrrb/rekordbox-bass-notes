// Parse a bass-profile token out of a Rekordbox comment, e.g. "B:l6m9h7".
// The preset letter is configurable server-side (default "B"); any single
// leading letter is accepted here. Band letters may be upper or lower case.

export interface BassDigits {
  l: number
  m: number
  h: number
}

// Sub-bass band edges in Hz, matching the backend's settings.band_edges_hz.
// Four edges → three log-spaced bands: L 20–39, M 39–77, H 77–150 Hz.
export const BAND_EDGES_HZ = [20, 39.15, 76.63, 150] as const

const TOKEN_RE = /[A-Za-z]:[Ll](\d)[Mm](\d)[Hh](\d)/

export function parseBassToken(comment: string | null | undefined): BassDigits | null {
  if (!comment) return null
  const m = TOKEN_RE.exec(comment)
  if (!m) return null
  return { l: Number(m[1]), m: Number(m[2]), h: Number(m[3]) }
}
