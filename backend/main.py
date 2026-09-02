"""FastAPI app.

  GET  /api/health
  GET  /api/tracks?search=&limit=
  GET  /api/tracks/{id}
  POST /api/tracks/{id}/analyze   -- audio analysis + proposed comment (no write)
  POST /api/tracks/analyze        -- same, batch, streamed as NDJSON (no write)
  PUT  /api/tracks/{id}/comment   -- write one comment (backup + commit)
  PUT  /api/tracks/comments       -- write many comments atomically (one backup)

Run:  .venv/bin/uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import dataclasses
import json
import logging
import mimetypes
import os
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import __version__

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, model_validator

from . import restore as restore_mod
from . import update_check
from .analysis import AudioDecodeError, BandResult, analyze_file, merge_token
from .config import settings
from .db import (
    DatabaseIntegrityError,
    RekordboxDB,
    RekordboxRunningError,
    Track,
    TrackNotFoundError,
    detect_library_path,
    rekordbox_agent_running,
    rekordbox_running,
)
from .logging_setup import log_path, read_tail, setup_logging
from .runtime import runtime

setup_logging()
log = logging.getLogger("backend.main")


@dataclass
class AnalyzeResponse:
    id: str
    title: str
    artist: str
    audio_path: str
    sample_rate: int
    duration_sec: float
    bands: list[BandResult]
    token: str
    current_comment: str
    proposed_comment: str
    merge_action: str  # "replaced" | "appended"
    existing_tokens: int


class CommentUpdate(BaseModel):
    """Exactly one of `token` (merge into the existing comment) or `comment`
    (replace it outright) must be provided."""

    token: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "CommentUpdate":
        if (self.token is None) == (self.comment is None):
            raise ValueError("provide exactly one of 'token' or 'comment'")
        return self


@dataclass
class CommentUpdateResult:
    id: str
    old_comment: str
    new_comment: str
    backup_path: str


class AnalyzeBatchRequest(BaseModel):
    ids: list[str]


class BatchCommentItem(BaseModel):
    id: str
    token: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "BatchCommentItem":
        if (self.token is None) == (self.comment is None):
            raise ValueError(f"item {self.id}: provide exactly one of 'token' or 'comment'")
        return self


class BatchCommentRequest(BaseModel):
    items: list[BatchCommentItem]


@dataclass
class BatchCommentResult:
    backup_path: str
    count: int
    results: list[dict]  # [{id, old_comment, new_comment}]


class DbSwitchRequest(BaseModel):
    target: str  # "live" (auto-locate) | "custom" (a chosen master.db path)
    path: Optional[str] = None

    @model_validator(mode="after")
    def _valid(self) -> "DbSwitchRequest":
        if self.target not in ("live", "custom"):
            raise ValueError("target must be 'live' or 'custom'")
        if self.target == "custom" and not self.path:
            raise ValueError("'custom' target requires 'path'")
        return self


_state: dict[str, Optional[RekordboxDB]] = {"db": None}
_swap_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        _state["db"] = RekordboxDB()
        log.info("opened database %s", _state["db"].db_path)
    except Exception as e:  # noqa: BLE001 - start anyway; the UI shows a locate screen
        _state["db"] = None
        log.warning("startup: no database open (%s: %s)", type(e).__name__, e)
    try:
        yield
    finally:
        cur = _state.get("db")
        if cur is not None:
            cur.close()
        _state["db"] = None


app = FastAPI(title="rekordbox bass notes", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if getattr(sys, "frozen", False) else [settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db() -> RekordboxDB:
    cur = _state.get("db")
    if cur is None:
        raise HTTPException(
            status_code=503,
            detail="No Rekordbox database is open — choose one from the header.",
        )
    return cur


def _same_path(a: str, b: Optional[str]) -> bool:
    if not b:
        return False
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except Exception:
        return a == b


def humanize(exc: Exception) -> tuple[int, str]:
    """Map an exception to (http_status, plain-language message)."""
    if isinstance(exc, RekordboxRunningError):
        return 409, "Rekordbox is still open — quit it and try again."
    if isinstance(exc, TrackNotFoundError):
        return 404, "That track is no longer in the library."
    if isinstance(exc, AudioDecodeError):
        return 422, str(exc)  # already phrased for humans
    if isinstance(exc, DatabaseIntegrityError):
        return 500, str(exc)  # names the backup to restore
    if isinstance(exc, FileNotFoundError):
        return 422, (
            "Couldn't find your Rekordbox library. Use “Change library…” "
            "to point at your master.db."
        )
    text = str(exc).lower()
    if "not a database" in text or "sqlcipher" in text or "decrypt" in text or "hmac" in text:
        return 422, (
            "Couldn't open that database — it may be a newer Rekordbox version "
            "than this build supports. Tell me your Rekordbox version."
        )
    return 500, f"{type(exc).__name__}: {exc}"


def _http(exc: Exception) -> HTTPException:
    status, msg = humanize(exc)
    return HTTPException(status_code=status, detail=msg)


@app.get("/api/health")
def health() -> dict:
    detected = detect_library_path()
    base = {
        "version": __version__,
        "detected_library_path": detected,
        "rekordbox_running": rekordbox_running(),
        "rekordbox_agent_running": rekordbox_agent_running(),
        "log_path": str(log_path()),
    }
    d = _state.get("db")
    if d is None:
        return {
            **base,
            "db_path": None,
            "db_kind": "none",  # no database open — UI shows the locate screen
            "track_count": None,
            "local_track_count": None,
        }
    current = str(d.db_path)
    return {
        **base,
        "db_path": current,
        "db_kind": "live" if _same_path(current, detected) else "custom",
        "track_count": d.count_tracks(),
        "local_track_count": d.count_local_tracks(),
    }


def _swap_db(new_path: str) -> None:
    """Reopen the shared RekordboxDB against ``new_path`` and persist the choice.
    Raises on open failure with the current DB left untouched."""
    with _swap_lock:
        try:
            new_db = RekordboxDB(new_path)
        except Exception as e:
            raise _http(e) from e
        old = _state.get("db")
        _state["db"] = new_db
        if old is not None:
            try:
                with old._lock:  # drain any in-flight operation before closing
                    old.close()
            except Exception:
                pass
        runtime.db_path = new_path
        runtime.save()


@app.post("/api/db/switch")
def switch_db(body: DbSwitchRequest) -> dict:
    """Reopen the backend against a different master.db at runtime, and remember
    the choice (persisted to config.json, so it survives a restart)."""
    new_path = "" if body.target == "live" else (body.path or "")
    _swap_db(new_path)
    return health()


# --- diagnostics & updates ------------------------------------------------
@app.get("/api/diagnostics", response_class=PlainTextResponse)
def diagnostics() -> str:
    """The tail of the app log, for a 'Copy diagnostics' button."""
    header = (
        f"rekordbox bass notes {__version__}\n"
        f"python {sys.version.split()[0]}  frozen={getattr(sys, 'frozen', False)}\n"
        f"log: {log_path()}\n"
        f"{'-' * 60}\n"
    )
    return header + read_tail()


class DismissUpdate(BaseModel):
    version: str


@app.get("/api/update-check")
def update_check_api(force: bool = Query(False)) -> dict:
    """Latest GitHub release vs. the running version (memoised ~1h). Includes
    ``last_seen`` so the UI can keep the banner dismissed per-version."""
    info = update_check.check(force=force).as_dict()
    info["last_seen"] = runtime.last_seen_version
    if info.get("latest") and not update_check.is_newer(
        info["latest"], runtime.last_seen_version or "0"
    ):
        info["update_available"] = False
    return info


@app.post("/api/update-check/dismiss")
def dismiss_update(body: DismissUpdate) -> dict:
    runtime.last_seen_version = body.version.strip()
    runtime.save()
    return {"last_seen": runtime.last_seen_version}


class OpenExternal(BaseModel):
    url: str


@app.post("/api/open-external")
def open_external(body: OpenExternal) -> dict:
    """Open a URL in the user's real browser (the packaged WebKit shell can't
    navigate away from the app itself)."""
    import webbrowser

    url = body.url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise HTTPException(status_code=422, detail="only http(s) URLs are allowed")
    webbrowser.open(url)
    return {"opened": url}


@app.post("/api/pick-file")
def pick_file_api() -> dict:
    """Open the OS 'choose a file' dialog (packaged app only). Returns the chosen
    path or ``{path: null}`` on cancel; 501 when there's no native shell."""
    from . import desktop

    if not desktop.has_file_picker():
        raise HTTPException(status_code=501, detail="Native file dialog isn't available here.")
    try:
        return {"path": desktop.pick_file()}
    except Exception as e:  # noqa: BLE001
        raise _http(e) from e


@app.get("/api/tracks", response_model=list[Track])
def list_tracks(
    search: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1),
) -> list[Track]:
    return db().list_tracks(search=search, limit=limit)


@app.get("/api/tracks/{track_id}", response_model=Track)
def get_track(track_id: str) -> Track:
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"No track with ID {track_id}")
    return track


@app.get("/api/tracks/{track_id}/audio")
def track_audio(track_id: str) -> FileResponse:
    """Stream the track's audio file (Range-enabled, for the in-app player)."""
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="That track is no longer in the library.")
    if not track.has_file:
        raise HTTPException(
            status_code=422, detail="This track's audio file has moved or is offline."
        )
    media_type = mimetypes.guess_type(track.folder_path)[0] or "application/octet-stream"
    return FileResponse(
        track.folder_path,
        media_type=media_type,
        filename=os.path.basename(track.folder_path),
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/tracks/{track_id}/analyze", response_model=AnalyzeResponse)
def analyze_track(track_id: str) -> AnalyzeResponse:
    """Analyse the track's audio and return the proposed comment. Does NOT write."""
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="That track is no longer in the library.")
    if not track.has_file:
        raise HTTPException(
            status_code=422,
            detail="This track's audio file has moved or is offline.",
        )
    try:
        res = analyze_file(track.folder_path)
    except Exception as e:  # noqa: BLE001 - surface decode/DSP failures to the client
        raise _http(e) from e

    merged = merge_token(track.comment, res.token)
    return AnalyzeResponse(
        id=track.id,
        title=track.title,
        artist=track.artist,
        audio_path=track.folder_path,
        sample_rate=res.sample_rate,
        duration_sec=res.duration_sec,
        bands=res.bands,
        token=res.token,
        current_comment=track.comment,
        proposed_comment=merged.comment,
        merge_action=merged.action,
        existing_tokens=merged.existing_tokens,
    )


@app.post("/api/tracks/analyze")
def analyze_batch(body: AnalyzeBatchRequest) -> StreamingResponse:
    """Analyse many tracks; stream one NDJSON record per track as it finishes.

    Each line: {id, index, total, ok, ...}. On ok: title, artist, token, bands,
    current_comment, proposed_comment, merge_action, existing_tokens. On not-ok:
    error. Never writes.
    """
    ids = body.ids
    database = db()

    def stream():
        total = len(ids)
        for i, track_id in enumerate(ids, 1):
            rec: dict = {"id": track_id, "index": i, "total": total}
            track = database.get_track(track_id)
            if track is None:
                rec |= {"ok": False, "error": "no longer in the library"}
            elif not track.has_file:
                rec |= {"ok": False, "error": "audio file has moved or is offline"}
            else:
                try:
                    res = analyze_file(track.folder_path)
                    merged = merge_token(track.comment, res.token)
                    rec |= {
                        "ok": True,
                        "title": track.title,
                        "artist": track.artist,
                        "audio_path": track.folder_path,
                        "sample_rate": res.sample_rate,
                        "duration_sec": res.duration_sec,
                        "token": res.token,
                        "bands": [dataclasses.asdict(b) for b in res.bands],
                        "current_comment": track.comment,
                        "proposed_comment": merged.comment,
                        "merge_action": merged.action,
                        "existing_tokens": merged.existing_tokens,
                    }
                except Exception as e:  # noqa: BLE001 - report per-track, keep going
                    rec |= {"ok": False, "error": humanize(e)[1]}
            yield json.dumps(rec) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.put("/api/tracks/comments", response_model=BatchCommentResult)
def update_comments(body: BatchCommentRequest) -> BatchCommentResult:
    """Write many comments in ONE transaction with ONE backup. All-or-nothing:
    if any id is unknown the whole batch is rejected and nothing is written."""
    if not body.items:
        raise HTTPException(status_code=422, detail="no items")
    ids = [it.id for it in body.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="duplicate track ids in batch")

    database = db()
    pairs: list[tuple[str, str]] = []
    for it in body.items:
        track = database.get_track(it.id)
        if track is None:
            raise HTTPException(status_code=404, detail=f"Track {it.id} is no longer in the library.")
        new_comment = (
            merge_token(track.comment, it.token).comment
            if it.token is not None
            else (it.comment or "")
        )
        pairs.append((it.id, new_comment))

    try:
        backup_path, changes = database.set_comments(pairs)
    except Exception as e:
        raise _http(e) from e

    return BatchCommentResult(
        backup_path=str(backup_path),
        count=len(changes),
        results=[
            {"id": tid, "old_comment": old, "new_comment": new}
            for tid, old, new in changes
        ],
    )


@app.put("/api/tracks/{track_id}/comment", response_model=CommentUpdateResult)
def update_comment(track_id: str, body: CommentUpdate) -> CommentUpdateResult:
    """Write the track's comment. Requires Rekordbox to be closed; backs up
    master.db first. `token` merges into the existing comment (see
    analysis.merge_token); `comment` replaces it outright."""
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="That track is no longer in the library.")

    if body.token is not None:
        new_comment = merge_token(track.comment, body.token).comment
    else:
        new_comment = body.comment or ""

    try:
        old, new, backup_path = db().set_comment(track_id, new_comment)
    except Exception as e:
        raise _http(e) from e

    return CommentUpdateResult(
        id=track_id, old_comment=old, new_comment=new, backup_path=str(backup_path)
    )


# --- backups ---------------------------------------------------------------
@app.get("/api/backups")
def list_backups_api() -> dict:
    d = _state.get("db")
    if d is None:
        live = {"db_path": None, "usn": None, "track_count": None, "tagged_count": None}
    else:
        try:
            live = {"db_path": str(d.db_path), **d.stats()}
        except Exception:  # noqa: BLE001
            live = {"db_path": str(d.db_path), "usn": None, "track_count": None, "tagged_count": None}
    infos = restore_mod.list_backups()
    return {
        "backup_dir": runtime.backup_dir,
        "live": live,
        "backups": [
            {
                "name": i.path.name,
                "taken": i.taken.isoformat() if i.taken else None,
                "size": i.size,
                "wal_size": i.wal_size,
                "shm_size": i.shm_size,
                "usn": i.usn,
                "track_count": i.track_count,
                "tagged_count": i.tagged_count,
                "recent": [{"title": t, "updated_at": u} for t, u in i.recent],
                "is_prerestore": "_prerestore" in i.path.name,
                "error": i.error,
            }
            for i in infos
        ],
    }


@app.post("/api/backups/{name}/restore")
def restore_backup_api(name: str) -> dict:
    """Restore a backup over the live database. Rekordbox must be closed. The
    current DB is snapshotted first (``*_prerestore.db``), so this is reversible."""
    old = _state.get("db")
    if old is None:
        raise HTTPException(status_code=503, detail="Open a database before restoring a backup.")
    if rekordbox_running():
        raise HTTPException(status_code=409, detail="Quit Rekordbox before restoring a backup.")
    infos = restore_mod.list_backups()
    try:
        chosen = restore_mod.resolve_backup(name, infos)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    with _swap_lock:
        live = old.db_path
        try:
            with old._lock:
                old.close()
            pre = restore_mod.apply_restore(chosen, live, Path(runtime.backup_dir))
            _state["db"] = RekordboxDB(str(live))
        except Exception as e:
            try:  # never leave the server without a DB handle
                _state["db"] = RekordboxDB(str(live))
            except Exception:
                pass
            raise _http(e) from e

    return {"restored_from": chosen.path.name, "prerestore_snapshot": pre.name, **health()}


# --- static SPA (packaged / one-process mode) --------------------------------
# Declared last so /api/* routes take precedence. In dev the frontend is served
# by `npm run dev`; this mount only matters when uvicorn serves the built app.
def _frontend_dist() -> Optional[str]:
    import sys
    from pathlib import Path

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    dist = base / "frontend" / "dist"
    return str(dist) if (dist / "index.html").is_file() else None


_dist = _frontend_dist()
if _dist:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_dist, html=True), name="spa")
