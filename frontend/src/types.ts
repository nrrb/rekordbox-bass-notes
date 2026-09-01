export interface Track {
  id: string
  title: string
  artist: string
  album: string
  genre: string
  comment: string
  folder_path: string
  has_file: boolean
}

export interface Health {
  db_path: string
  db_kind: 'live' | 'custom'
  detected_library_path: string | null
  rekordbox_running: boolean
  track_count: number
  local_track_count: number
}

export interface BandResult {
  band: 'L' | 'M' | 'H'
  hz_low: number
  hz_high: number
  rms: number
  dbfs: number
  digit: number
}

export interface CommentUpdateResult {
  id: string
  old_comment: string
  new_comment: string
  backup_path: string
}

export interface BatchAnalyzeItem {
  id: string
  index: number
  total: number
  ok: boolean
  error?: string
  title?: string
  artist?: string
  token?: string
  bands?: BandResult[]
  current_comment?: string
  proposed_comment?: string
  merge_action?: 'replaced' | 'prepended'
  existing_tokens?: number
}

export interface BatchCommentResult {
  backup_path: string
  count: number
  results: { id: string; old_comment: string; new_comment: string }[]
}

export interface AnalyzeResponse {
  id: string
  title: string
  artist: string
  audio_path: string
  sample_rate: number
  duration_sec: number
  bands: BandResult[]
  token: string
  current_comment: string
  proposed_comment: string
  merge_action: 'replaced' | 'prepended'
  existing_tokens: number
}
