"""File logging for the packaged app.

One rotating log file so a friend can hit "Copy diagnostics" and paste something
useful when things break in the field.

  - frozen app: ``~/Library/Logs/rekordbox bass notes/app.log``
  - dev:        ``<repo>/.logs/app.log``  (gitignored)

``setup_logging()`` is idempotent — safe to call from both ``launcher.py`` and
``backend.main`` import.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import _REPO_ROOT

APP_NAME = "rekordbox bass notes"
_FROZEN = bool(getattr(sys, "frozen", False))

_MAX_BYTES = 1_000_000
_BACKUPS = 3
_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_configured = False


def log_dir() -> Path:
    if _FROZEN:
        return Path.home() / "Library" / "Logs" / APP_NAME
    return _REPO_ROOT / ".logs"


def log_path() -> Path:
    return log_dir() / "app.log"


def setup_logging(level: int = logging.INFO) -> Path:
    """Attach a rotating file handler (+ stderr) to the root logger once."""
    global _configured
    p = log_path()
    if _configured:
        return p

    p.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    fh = logging.handlers.RotatingFileHandler(
        p, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)

    # keep console output too (uvicorn --reload dev loop, and the frozen app's
    # stderr which pywebview/Console.app can still capture)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(sh)

    # uvicorn installs its own handlers; let its records propagate to root so
    # they land in the file too, without doubling on the console.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True
    logging.getLogger(__name__).info("logging to %s", p)
    return p


def read_tail(max_bytes: int = 64_000) -> str:
    """The tail of the current log file, for a 'Copy diagnostics' action."""
    p = log_path()
    try:
        data = p.read_bytes()
    except FileNotFoundError:
        return f"(no log file at {p})"
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", "replace")
