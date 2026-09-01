"""FastAPI app.

Read-only endpoints:
  GET  /api/health
  GET  /api/tracks?search=&limit=
  GET  /api/tracks/{id}
  POST /api/tracks/{id}/analyze   -- audio analysis + proposed comment (no write)

Run:  .venv/bin/uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analysis import BandResult, analyze_file, merge_token
from .config import settings
from .db import RekordboxDB, Track, rekordbox_running


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
    return {
        "db_path": settings.db_path or "(auto-located)",
        "rekordbox_running": rekordbox_running(),
        "track_count": db().count_tracks(),
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
