"""FastAPI app.

  GET  /api/health
  GET  /api/tracks?search=&limit=
  GET  /api/tracks/{id}
  POST /api/tracks/{id}/analyze   -- audio analysis + proposed comment (no write)
  PUT  /api/tracks/{id}/comment   -- write the comment (backup + commit)

Run:  .venv/bin/uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator

from .analysis import BandResult, analyze_file, merge_token
from .config import settings
from .db import RekordboxDB, RekordboxRunningError, Track, TrackNotFoundError, rekordbox_running


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

_state: dict[str, RekordboxDB] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _state["db"] = RekordboxDB()
    try:
        yield
    finally:
        _state["db"].close()
        _state.clear()


app = FastAPI(title="Rekordbox Comment Tagger", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db() -> RekordboxDB:
    return _state["db"]


@app.get("/api/health")
def health() -> dict:
    d = db()
    return {
        "db_path": settings.db_path or "(auto-located)",
        "rekordbox_running": rekordbox_running(),
        "track_count": d.count_tracks(),
        "local_track_count": d.count_local_tracks(),
    }


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


@app.post("/api/tracks/{track_id}/analyze", response_model=AnalyzeResponse)
def analyze_track(track_id: str) -> AnalyzeResponse:
    """Analyse the track's audio and return the proposed comment. Does NOT write."""
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"No track with ID {track_id}")
    if not track.has_file:
        raise HTTPException(
            status_code=422,
            detail=f"Track has no local audio file: {track.folder_path or '(empty)'}",
        )
    try:
        res = analyze_file(track.folder_path)
    except Exception as e:  # noqa: BLE001 - surface decode/DSP failures to the client
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

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


@app.put("/api/tracks/{track_id}/comment", response_model=CommentUpdateResult)
def update_comment(track_id: str, body: CommentUpdate) -> CommentUpdateResult:
    """Write the track's comment. Requires Rekordbox to be closed; backs up
    master.db first. `token` merges into the existing comment (see
    analysis.merge_token); `comment` replaces it outright."""
    track = db().get_track(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"No track with ID {track_id}")

    if body.token is not None:
        new_comment = merge_token(track.comment, body.token).comment
    else:
        new_comment = body.comment or ""

    try:
        old, new, backup_path = db().set_comment(track_id, new_comment)
    except RekordboxRunningError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TrackNotFoundError:
        raise HTTPException(status_code=404, detail=f"No track with ID {track_id}")
    except Exception as e:  # noqa: BLE001 - surface commit failures to the client
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

    return CommentUpdateResult(
        id=track_id, old_comment=old, new_comment=new, backup_path=str(backup_path)
    )
