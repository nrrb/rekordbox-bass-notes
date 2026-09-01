"""Backend configuration.

Every value can be overridden with an environment variable (named in each
default below). Import ``settings`` from here; it is a frozen singleton.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DB_PATH = str(_REPO_ROOT / "sample" / "master.db")


def _s(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _i(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


def _f(key: str, default: float) -> float:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


def _b(key: str, default: bool = False) -> bool:
    v = os.environ.get(key)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _resolve_db_path() -> str:
    """Empty string => pyrekordbox auto-locates the live library."""
    if _b("USE_LIVE_LIBRARY"):
        return ""
    return _s("REKORDBOX_DB_PATH", SAMPLE_DB_PATH)


@dataclass(frozen=True)
class Settings:
    # --- database ---
    # Path to master.db (the file or its parent dir). Defaults to the bundled
    # sample copy. `REKORDBOX_DB_PATH=""` or `USE_LIVE_LIBRARY=1` => pyrekordbox
    # auto-locates the live library.
    db_path: str = field(default_factory=_resolve_db_path)
    result_limit: int = field(default_factory=lambda: _i("RESULT_LIMIT", 500))

    # --- CORS ---
    frontend_origin: str = field(
        default_factory=lambda: _s("FRONTEND_ORIGIN", "http://localhost:5173")
    )

    # --- audio analysis (used from build step 3 on) ---
    # 500 Hz: Nyquist 250 Hz >> 150 Hz, and the low normalised band edges stay
    # well-conditioned for an order-8 Butterworth (max |pole| ~0.98).
    audio_sr: int = field(default_factory=lambda: _i("AUDIO_SR", 500))
    audio_res_type: str = field(
        default_factory=lambda: _s("AUDIO_RES_TYPE", "soxr_hq")
    )
    # log-spaced thirds of 20-150 Hz: [low, lo/mid split, mid/high split, high]
    # == 20 * (150/20) ** (k/3) for k in 0..3
    band_edges_hz: tuple[float, float, float, float] = (20.0, 39.15, 76.63, 150.0)
    # dBFS -> digit endpoints, per band: min -> digit 0, max -> digit 9 (linear).
    # ABSOLUTE scale -- referenced to digital full scale, not track loudness --
    # so a given dBFS always yields the same digit, comparable across any tracks
    # (present or future). Values calibrated from the p5/p95 of a 117-track
    # sample; see backend/calibrate.py. Freeze once tokens are written to the
    # real DB; a later recalibration must bump preset_letter (B -> C) so mixed
    # vintages stay distinguishable.
    dbfs_scale: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "L": (_f("DBFS_MIN_L", -46.0), _f("DBFS_MAX_L", -18.0)),
            "M": (_f("DBFS_MIN_M", -23.0), _f("DBFS_MAX_M", -7.0)),
            "H": (_f("DBFS_MIN_H", -20.0), _f("DBFS_MAX_H", -9.0)),
        }
    )
    preset_letter: str = field(default_factory=lambda: _s("PRESET_LETTER", "B"))
    filter_order: int = field(default_factory=lambda: _i("FILTER_ORDER", 8))
    comment_sep: str = field(default_factory=lambda: _s("COMMENT_SEP", " "))

    # --- backups ---
    backup_dir: str = field(
        default_factory=lambda: _s(
            "BACKUP_DIR", str(_REPO_ROOT / "backend" / "backups")
        )
    )
    # keep at most this many backup sets (master.db + -wal/-shm); oldest pruned
    # after each new backup. 0 disables pruning (keep everything).
    backup_keep: int = field(default_factory=lambda: _i("BACKUP_KEEP", 20))


settings = Settings()
