"""Thin wrapper around pyrekordbox for reading and writing track comments in
the Rekordbox 6/7 library database.

Write path notes (see pyrekordbox.db6.tables.Base.__setattr__ /
db6.registry.RekordboxAgentRegistry / db6.database.Rekordbox6Database.commit):
plain attribute assignment (``content.Commnt = x``) is intercepted and queued
by the ORM base class; ``db.commit()`` walks that queue, bumps the global
``agentRegistry`` USN and each changed row's ``rb_local_usn`` to match, *then*
issues the SQL commit. So ``content.Commnt = x; db.commit()`` is the complete,
sync-safe write -- no manual USN bookkeeping needed. ``commit()`` also checks
for a running Rekordbox process itself and raises ``RuntimeError`` if so; we
still pre-check with ``rekordbox_running()`` to fail fast and give a clean 409
before doing any work, and catch the library's own check as a fallback for the
race where Rekordbox launches in between.
"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdContent
from sqlalchemy import text

from .config import settings


class RekordboxRunningError(RuntimeError):
    """Rekordbox is open; refusing to write to master.db."""


class TrackNotFoundError(KeyError):
    """No track with the given ID."""


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
        # resolved path to the actual master.db file, for backups
        self.db_path = Path(str(self._db.engine.url.database)).resolve()

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ reads
    def count_tracks(self) -> int:
        return sum(1 for _ in self._db.get_content())

    def count_local_tracks(self) -> int:
        return sum(1 for c in self._db.get_content() if Track.from_content(c).has_file)

    def list_tracks(
        self, search: Optional[str] = None, limit: Optional[int] = None
    ) -> list[Track]:
        """Only tracks backed by a local audio file on disk. Streaming entries
        and tracks whose file is missing/relocated are excluded."""
        cap = settings.result_limit if limit is None else limit
        needle = (search or "").strip().lower()
        out: list[Track] = []
        for c in self._db.get_content():
            t = Track.from_content(c)
            if not t.has_file:
                continue
            if needle and needle not in f"{t.title} {t.artist} {t.album}".lower():
                continue
            out.append(t)
            if len(out) >= cap:
                break
        return out

    def get_track(self, track_id: str) -> Optional[Track]:
        content = self._get_raw_content(track_id)
        return Track.from_content(content) if content is not None else None

    def _get_raw_content(self, track_id: str) -> Optional[DjmdContent]:
        """The live ORM row (for mutation), not a Track snapshot."""
        try:
            res = self._db.get_content(ID=track_id)
        except Exception:
            return None
        if res is None:
            return None
        return res if isinstance(res, DjmdContent) else res.first()

    # ----------------------------------------------------------------- writes
    def backup(self) -> Path:
        """Checkpoint the WAL and copy master.db (+ -wal/-shm) to backup_dir.

        master.db runs in WAL mode: a plain copy of the main file can miss
        recent writes sitting in the -wal sidecar. Checkpointing folds those
        back in before we copy, and we copy the sidecars too as a second line
        of defense.
        """
        try:
            self._db.session.execute(text("PRAGMA wal_checkpoint(FULL)"))
        except Exception:
            pass  # best-effort; the sidecar copies below still protect us

        out_dir = Path(settings.backup_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%S")
        dest = out_dir / f"{self.db_path.stem}_{ts}{self.db_path.suffix}"
        shutil.copy2(self.db_path, dest)
        for suffix in ("-wal", "-shm"):
            side = self.db_path.with_name(self.db_path.name + suffix)
            if side.exists():
                shutil.copy2(side, dest.with_name(dest.name + suffix))
        return dest

    def set_comment(self, track_id: str, new_comment: str) -> tuple[str, str, Path]:
        """Set ``Commnt`` on a track and commit. Returns (old, new, backup_path).

        Order: refuse-if-running guard -> backup -> capture old -> mutate ->
        commit (which itself re-checks Rekordbox and bumps USN bookkeeping).

        Raises:
            RekordboxRunningError: Rekordbox is open.
            TrackNotFoundError: no track with ``track_id``.
        """
        if rekordbox_running():
            raise RekordboxRunningError("Rekordbox is running; quit it and retry.")

        content = self._get_raw_content(track_id)
        if content is None:
            raise TrackNotFoundError(track_id)

        backup_path = self.backup()
        old = content.Commnt or ""
        content.Commnt = new_comment
        try:
            self._db.commit()
        except RuntimeError as e:
            # pyrekordbox's own guard: Rekordbox launched between our pre-check
            # and commit(). Discard the uncommitted change.
            self._db.session.rollback()
            raise RekordboxRunningError(str(e)) from e
        return old, new_comment, backup_path


def rekordbox_running() -> bool:
    """True if a Rekordbox process is running (the DB must be closed to write)."""
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        if name == "rekordbox" or name.startswith("rekordbox"):
            return True
    return False
