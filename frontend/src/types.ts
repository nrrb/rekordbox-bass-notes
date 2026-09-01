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
  rekordbox_running: boolean
  track_count: number
}
