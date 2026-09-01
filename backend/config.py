"""Backend configuration.

Every value can be overridden with an environment variable (named in each
default below). Import ``settings`` from here; it is a frozen singleton.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


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


@dataclass(frozen=True)
class Settings:
    # --- database ---
    # Path to master.db (the file or its parent dir). Defaults to the bundled
    # sample copy. Set REKORDBOX_DB_PATH="" to let pyrekordbox auto-locate the
    # live database.
    db_path: str = field(
        default_factory=lambda: _s(
            "REKORDBOX_DB_PATH", str(_REPO_ROOT / "sample" / "master.db")
        )
    )
    result_limit: int = field(default_factory=lambda: _i("RESULT_LIMIT", 500))

    # --- CORS ---
    frontend_origin: str = field(
        default_factory=lambda: _s("FRONTEND_ORIGIN", "http://localhost:5173")
    )

    # --- audio analysis (used from build step 3 on) ---
    audio_sr: int = field(default_factory=lambda: _i("AUDIO_SR", 2000))
    # log-spaced thirds of 20-150 Hz: [low, lo/mid split, mid/high split, high]
    band_edges_hz: tuple[float, float, float, float] = (20.0, 39.1, 76.6, 150.0)
    dbfs_min: float = field(default_factory=lambda: _f("DBFS_MIN", -48.0))
    dbfs_max: float = field(default_factory=lambda: _f("DBFS_MAX", -6.0))
    preset_letter: str = field(default_factory=lambda: _s("PRESET_LETTER", "B"))
    filter_order: int = field(default_factory=lambda: _i("FILTER_ORDER", 8))
    comment_sep: str = field(default_factory=lambda: _s("COMMENT_SEP", " "))

    # --- backups ---
    backup_dir: str = field(
        default_factory=lambda: _s(
            "BACKUP_DIR", str(_REPO_ROOT / "backend" / "backups")
        )
    )


settings = Settings()
