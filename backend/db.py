"""Thin wrapper around pyrekordbox for reading (and, from step 5, writing)
track comments in the Rekordbox 6/7 library database."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import psutil
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdContent

from .config import settings


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    genre: str
    comment: str
    folder_path: str
    has_file: bool

    @classmethod
    def from_content(cls, c: DjmdContent) -> "Track":
        path = c.FolderPath or ""
        return cls(
            id=str(c.ID),
            title=c.Title or "",
            artist=c.ArtistName or "",
            album=c.AlbumName or "",
            genre=c.GenreName or "",
            comment=c.Commnt or "",
            folder_path=path,
            # streaming entries store a URI like "apple-music:tracks:123" in
            # FolderPath; only real local files are analysable.
            has_file=bool(path) and os.path.isfile(path),
        )


class RekordboxDB:
    """Opens the database once and holds the session for the app lifetime.

    Fine for a single-user local tool; not for concurrent writers.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        path = settings.db_path if db_path is None else db_path
        self._db = Rekordbox6Database(path) if path else Rekordbox6Database()

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ reads
    def count_tracks(self) -> int:
        return sum(1 for _ in self._db.get_content())

    def list_tracks(
        self, search: Optional[str] = None, limit: Optional[int] = None
    ) -> list[Track]:
        cap = settings.result_limit if limit is None else limit
        needle = (search or "").strip().lower()
        out: list[Track] = []
        for c in self._db.get_content():
            t = Track.from_content(c)
            if needle and needle not in f"{t.title} {t.artist} {t.album}".lower():
                continue
            out.append(t)
            if len(out) >= cap:
                break
        return out

    def get_track(self, track_id: str) -> Optional[Track]:
        try:
            res = self._db.get_content(ID=track_id)
        except Exception:
            return None
        if res is None:
            return None
        content = res if isinstance(res, DjmdContent) else res.first()
        return Track.from_content(content) if content is not None else None


def rekordbox_running() -> bool:
    """True if a Rekordbox process is running (the DB must be closed to write)."""
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        if name == "rekordbox" or name.startswith("rekordbox"):
            return True
    return False
