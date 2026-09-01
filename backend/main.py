"""FastAPI app.

Step 1 scope: read-only endpoints.
  GET /api/health
  GET /api/tracks?search=&limit=
  GET /api/tracks/{id}

Run:  .venv/bin/uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import RekordboxDB, Track, rekordbox_running

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
