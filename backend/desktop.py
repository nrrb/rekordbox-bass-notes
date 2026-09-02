"""Bridge for desktop-shell features the web layer can't do itself.

``launcher.py`` (the pywebview host) registers a native "open file" picker here;
``main.py`` exposes it at ``/api/pick-file``. In dev / plain-browser mode nothing
is registered and the endpoint reports it's unavailable, so the UI falls back to
its plain text path field.
"""
from __future__ import annotations

from typing import Callable, Optional

# () -> selected absolute path, or None if the user cancelled.
_file_picker: Optional[Callable[[], Optional[str]]] = None


def set_file_picker(fn: Optional[Callable[[], Optional[str]]]) -> None:
    global _file_picker
    _file_picker = fn


def has_file_picker() -> bool:
    return _file_picker is not None


def pick_file() -> Optional[str]:
    if _file_picker is None:
        raise RuntimeError("no native file picker registered (not running in the app shell)")
    return _file_picker()
