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

import functools
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypeVar

import psutil
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdContent
from sqlalchemy import text

from .config import settings
from .runtime import runtime


class RekordboxRunningError(RuntimeError):
    """Rekordbox is open; refusing to write to master.db."""


class TrackNotFoundError(KeyError):
    """No track with the given ID."""


class DatabaseIntegrityError(RuntimeError):
    """A post-write ``PRAGMA quick_check`` did not return 'ok'."""


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


_F = TypeVar("_F", bound=Callable)


def _locked(method: _F) -> _F:
    """Serialise a public method behind ``self._lock``.

    The one shared ``RekordboxDB`` is reached from several uvicorn threadpool
    threads (sync endpoints run there). A SQLAlchemy ``Session`` is not
    thread-safe, so every public entry point takes this reentrant lock;
    internal helpers assume it is already held.
    """

    @functools.wraps(method)
    def wrapper(self: "RekordboxDB", *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class RekordboxDB:
    """Opens the database once and holds the session for the app lifetime.

    Single-user only. All DB access is serialised by ``self._lock`` (see
    ``_locked``); there is still no protection against a *second process*
    writing concurrently.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        path = runtime.db_path if db_path is None else db_path
        self._db = Rekordbox6Database(path) if path else Rekordbox6Database()
        # resolved path to the actual master.db file, for backups
        self.db_path = Path(str(self._db.engine.url.database)).resolve()
        self._lock = threading.RLock()

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ reads
    @_locked
    def count_tracks(self) -> int:
        return sum(1 for _ in self._db.get_content())

    @_locked
    def count_local_tracks(self) -> int:
        return sum(1 for c in self._db.get_content() if Track.from_content(c).has_file)

    @_locked
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

    @_locked
    def get_track(self, track_id: str) -> Optional[Track]:
        content = self._get_raw_content(track_id)
        return Track.from_content(content) if content is not None else None

    @_locked
    def stats(self) -> dict:
        """Identifying counts for the open DB: global USN, tracks, tagged tracks."""
        sess = self._db.session
        glob = f"*{settings.preset_letter}:[Ll][0-9][Mm][0-9][Hh][0-9]*"
        return {
            "usn": sess.execute(
                text("SELECT int_1 FROM agentRegistry WHERE registry_id='localUpdateCount'")
            ).scalar(),
            "track_count": sess.execute(text("SELECT COUNT(*) FROM djmdContent")).scalar(),
            "tagged_count": sess.execute(
                text("SELECT COUNT(*) FROM djmdContent WHERE Commnt GLOB :g"), {"g": glob}
            ).scalar(),
        }

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
    BACKUP_TS_FMT = "%Y%m%dT%H%M%S_%f"  # microseconds -> no same-second collisions

    @_locked
    def backup(self) -> Path:
        """Checkpoint the WAL and copy master.db (+ -wal/-shm) to backup_dir,
        then prune old backup sets down to ``settings.backup_keep``.

        master.db runs in WAL mode: a plain copy of the main file can miss
        recent writes sitting in the -wal sidecar. Checkpointing folds those
        back in before we copy, and we copy the sidecars too as a second line
        of defense.
        """
        try:
            self._db.session.execute(text("PRAGMA wal_checkpoint(FULL)"))
        except Exception:
            pass  # best-effort; the sidecar copies below still protect us

        out_dir = Path(runtime.backup_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime(self.BACKUP_TS_FMT)
        dest = out_dir / f"{self.db_path.stem}_{ts}{self.db_path.suffix}"
        shutil.copy2(self.db_path, dest)
        for suffix in ("-wal", "-shm"):
            side = self.db_path.with_name(self.db_path.name + suffix)
            if side.exists():
                shutil.copy2(side, dest.with_name(dest.name + suffix))
        self._prune_backups()
        return dest

    def _prune_backups(self) -> None:
        """Keep only the newest ``settings.backup_keep`` backup sets."""
        keep = settings.backup_keep
        if keep <= 0:
            return
        out_dir = Path(runtime.backup_dir)
        mains = sorted(out_dir.glob(f"{self.db_path.stem}_*{self.db_path.suffix}"))
        for main in mains[:-keep]:
            for p in (main, main.with_name(main.name + "-wal"),
                      main.with_name(main.name + "-shm")):
                p.unlink(missing_ok=True)

    @_locked
    def set_comment(self, track_id: str, new_comment: str) -> tuple[str, str, Path]:
        """Set ``Commnt`` on a track and commit. Returns (old, new, backup_path).

        Order: refuse-if-running guard -> backup -> capture old -> mutate ->
        commit (which itself re-checks Rekordbox and bumps USN bookkeeping) ->
        PRAGMA quick_check.

        Raises:
            RekordboxRunningError: Rekordbox is open.
            TrackNotFoundError: no track with ``track_id``.
            DatabaseIntegrityError: post-write integrity check failed (the
                pre-write backup path is in the message).
        """
        if rekordbox_running():
            raise RekordboxRunningError("Rekordbox is running; quit it and retry.")

        self._reset_session()
        content = self._get_raw_content(track_id)
        if content is None:
            raise TrackNotFoundError(track_id)

        backup_path = self.backup()
        old = content.Commnt or ""
        content.Commnt = new_comment
        self._commit_and_verify(backup_path)
        return old, new_comment, backup_path

    @_locked
    def set_comments(
        self, pairs: list[tuple[str, str]]
    ) -> tuple[Path, list[tuple[str, str, str]]]:
        """Atomically set ``Commnt`` on many tracks. ``pairs`` = [(track_id,
        new_comment), ...]. One backup, one commit, one quick_check.

        If any id is unknown, raises ``TrackNotFoundError`` (listing them) before
        anything is written. Returns (backup_path, [(id, old, new), ...]).
        """
        if not pairs:
            raise ValueError("no tracks given")
        if rekordbox_running():
            raise RekordboxRunningError("Rekordbox is running; quit it and retry.")

        self._reset_session()
        resolved: list[tuple[str, DjmdContent]] = []
        missing: list[str] = []
        for track_id, _ in pairs:
            content = self._get_raw_content(track_id)
            if content is None:
                missing.append(track_id)
            else:
                resolved.append((track_id, content))
        if missing:
            raise TrackNotFoundError(", ".join(missing))

        backup_path = self.backup()
        changes: list[tuple[str, str, str]] = []
        for (track_id, content), (_, new_comment) in zip(resolved, pairs):
            old = content.Commnt or ""
            content.Commnt = new_comment
            changes.append((track_id, old, new_comment))
        self._commit_and_verify(backup_path)
        return backup_path, changes

    def _reset_session(self) -> None:
        """Clear any half-open transaction / stale identity map left by a prior
        operation before starting a write. Cheap no-op on a clean session."""
        try:
            self._db.session.rollback()
        except Exception:
            pass

    def _commit_and_verify(self, backup_path: Path) -> None:
        try:
            self._db.commit()
        except RuntimeError as e:
            # pyrekordbox's own guard: Rekordbox launched between our pre-check
            # and commit(). Discard the uncommitted change(s).
            self._db.session.rollback()
            raise RekordboxRunningError(str(e)) from e

        result = self._db.session.execute(text("PRAGMA quick_check")).scalar()
        if result != "ok":
            raise DatabaseIntegrityError(
                f"post-write PRAGMA quick_check returned {result!r}. The write "
                f"may have left master.db inconsistent. Restore the pre-write "
                f"backup: {backup_path}  (python -m backend.restore <name>)"
            )


def _any_process_named(target: str) -> bool:
    """True if any running process's name (minus a Windows ``.exe``, trimmed and
    case-folded) is exactly ``target``."""
    for p in psutil.process_iter(["name"]):
        if os.path.splitext(p.info.get("name") or "")[0].strip().lower() == target:
            return True
    return False


def rekordbox_running() -> bool:
    """True if the Rekordbox desktop app itself is running.

    Matches a process named exactly ``rekordbox`` — the same test pyrekordbox's
    ``commit()`` guard uses (``utils.get_process_id``), so this pre-check and the
    library's own check always agree. A *prefix* match would also catch this
    app's own ``rekordbox bass notes`` process (packaged), permanently blocking
    every write, so the match is exact.

    ``rekordboxAgent`` (cloud/library sync) is intentionally not matched here —
    it doesn't hold the master.db write lock. See ``rekordbox_agent_running``.
    """
    return _any_process_named("rekordbox")


def rekordbox_agent_running() -> bool:
    """True if ``rekordboxAgent`` (the cloud / library-sync helper) is running.

    It frequently keeps running as a login item after Rekordbox itself is quit.
    Advisory only: it does not block writes, but the UI uses it to suggest
    pausing sync so Rekordbox's cloud sync doesn't race a write to master.db.
    """
    return _any_process_named("rekordboxagent")


def detect_library_path() -> Optional[str]:
    """The real Rekordbox library ``master.db``, from pyrekordbox's own config
    discovery. Returns ``None`` if none is found. Does not open the database."""
    try:
        from pyrekordbox.config import get_config

        for version in ("rekordbox7", "rekordbox6"):
            path = get_config(version, "db_path")
            if path:
                return str(path)
    except Exception:
        pass
    return None
