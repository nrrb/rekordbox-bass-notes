"""In-app update check against GitHub Releases.

The app is shared privately; there is no auto-install. On launch the UI calls
``/api/update-check`` and, if a newer tag exists, shows a dismissible
"vX.Y.Z is available" banner linking to the release page.

Configure the source repo with ``UPDATE_REPO`` (``owner/repo``). Unset ⇒ the
endpoint reports ``supported: false`` and the UI shows nothing. A private repo
needs ``UPDATE_GITHUB_TOKEN`` (a fine-grained PAT with read-only "Contents" or
"Releases" access) for the API call to succeed.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import __version__

_CACHE_TTL = 3600  # seconds; GitHub's unauthenticated limit is 60 req/h
_TIMEOUT = 6

_cache: dict[str, object] = {"at": 0.0, "payload": None}


def _repo() -> str:
    return os.environ.get("UPDATE_REPO", "").strip()


def _parse_version(tag: str) -> tuple[int, ...]:
    """``v1.2.3`` / ``1.2.3`` -> ``(1, 2, 3)``. Non-numeric parts drop to 0 so a
    malformed tag simply sorts low rather than raising."""
    core = tag.strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    out: list[int] = []
    for part in core.split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


@dataclass
class UpdateInfo:
    supported: bool
    current: str
    latest: Optional[str] = None
    update_available: bool = False
    url: Optional[str] = None
    notes: Optional[str] = None
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _fetch_latest_release(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "rekordbox-bass-notes-update-check",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("UPDATE_GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(force: bool = False) -> UpdateInfo:
    """Latest-release info, memoised for an hour. Never raises."""
    repo = _repo()
    if not repo:
        return UpdateInfo(supported=False, current=__version__)

    now = time.time()
    cached = _cache.get("payload")
    if not force and cached is not None and now - float(_cache["at"]) < _CACHE_TTL:
        return cached  # type: ignore[return-value]

    try:
        data = _fetch_latest_release(repo)
        tag = (data.get("tag_name") or data.get("name") or "").strip()
        if not tag:
            info = UpdateInfo(supported=True, current=__version__, error="no tagged release")
        else:
            info = UpdateInfo(
                supported=True,
                current=__version__,
                latest=tag,
                update_available=is_newer(tag, __version__),
                url=data.get("html_url"),
                notes=(data.get("body") or "").strip()[:2000] or None,
            )
    except Exception as e:  # noqa: BLE001 - network/parse/auth: report, don't crash
        info = UpdateInfo(supported=True, current=__version__, error=f"{type(e).__name__}: {e}")

    _cache["at"] = now
    _cache["payload"] = info
    return info
