"""Runtime (user-settable, persisted) configuration.

``settings`` (config.py) holds the static/env knobs — audio params, dbfs_scale,
preset letter, etc. This holds the two things an end user changes and that must
survive a restart: which ``master.db`` to use and where backups go.

Persisted to JSON:
  - frozen app: ``~/Library/Application Support/rekordbox bass notes/config.json``
  - dev:        ``<repo>/.rkbx-config.json``  (gitignored)

Precedence for each field: environment variable > config.json > built-in default.
The built-in default database is the real Rekordbox library, auto-located by
pyrekordbox (represented here as an empty string).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import _REPO_ROOT, _b

APP_NAME = "rekordbox bass notes"
_FROZEN = bool(getattr(sys, "frozen", False))


def config_path() -> Path:
    if _FROZEN:
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / APP_NAME
            / "config.json"
        )
    return _REPO_ROOT / ".rkbx-config.json"


def _default_db_path() -> str:
    # "" -> pyrekordbox auto-locates the real Rekordbox library.
    return ""


def _default_backup_dir() -> str:
    if _FROZEN:
        return str(Path.home() / "Music" / f"{APP_NAME} Backups")
    return str(_REPO_ROOT / "backend" / "backups")


def _env_db_path() -> str | None:
    """Env override, or None if the environment says nothing."""
    if _b("USE_LIVE_LIBRARY"):
        return ""  # auto-locate
    return os.environ.get("REKORDBOX_DB_PATH")  # None if unset; "" is a valid value


@dataclass
class RuntimeConfig:
    db_path: str = ""
    backup_dir: str = ""
    # last release the user acknowledged in the "update available" banner; the
    # banner stays hidden while this equals (or is newer than) the latest tag.
    last_seen_version: str = ""

    def load(self) -> "RuntimeConfig":
        try:
            data = json.loads(config_path().read_text())
        except (FileNotFoundError, ValueError):
            data = {}

        env_db = _env_db_path()
        self.db_path = (
            env_db
            if env_db is not None
            else (data.get("db_path") or _default_db_path())
        )
        self.backup_dir = (
            os.environ.get("BACKUP_DIR")
            or data.get("backup_dir")
            or _default_backup_dir()
        )
        self.last_seen_version = data.get("last_seen_version") or ""
        return self

    def save(self) -> None:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "db_path": self.db_path,
                    "backup_dir": self.backup_dir,
                    "last_seen_version": self.last_seen_version,
                },
                indent=2,
            )
        )


runtime = RuntimeConfig().load()
