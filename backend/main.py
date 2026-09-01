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
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from .analysis import BandResult, analyze_file, merge_token
from .config import SAMPLE_DB_PATH, settings
from .db import (
    RekordboxDB,
    RekordboxRunningError,
    Track,
    TrackNotFoundError,
    detect_library_path,
    rekordbox_running,
)


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


def _same_path(a: str, b: Optional[str]) -> bool:
    if not b:
        return False
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except Exception:
        return a == b


@app.get("/api/health")
def health() -> dict:
    d = db()
    current = str(d.db_path)
    detected = detect_library_path()
    if _same_path(current, detected):
        db_kind = "live"
    elif _same_path(current, SAMPLE_DB_PATH):
        db_kind = "sample"
    else:
        db_kind = "custom"
    return {
        "db_path": current,
        "db_kind": db_kind,  # "live" | "sample" | "custom"
        "detected_library_path": detected,
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
                rec |= {"ok": False, "error": "unknown track id"}
            elif not track.has_file:
                rec |= {"ok": False, "error": "no local audio file"}
            else:
                try:
                    res = analyze_file(track.folder_path)
                    merged = merge_token(track.comment, res.token)
                    rec |= {
                        "ok": True,
                        "title": track.title,
                        "artist": track.artist,
                        "token": res.token,
                        "bands": [dataclasses.asdict(b) for b in res.bands],
                        "current_comment": track.comment,
                        "proposed_comment": merged.comment,
                        "merge_action": merged.action,
                        "existing_tokens": merged.existing_tokens,
                    }
                except Exception as e:  # noqa: BLE001 - report per-track, keep going
                    rec |= {"ok": False, "error": f"{type(e).__name__}: {e}"}
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
            raise HTTPException(status_code=404, detail=f"No track with ID {it.id}")
        new_comment = (
            merge_token(track.comment, it.token).comment
            if it.token is not None
            else (it.comment or "")
        )
        pairs.append((it.id, new_comment))

    try:
        backup_path, changes = database.set_comments(pairs)
    except RekordboxRunningError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TrackNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Unknown track id(s): {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

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
