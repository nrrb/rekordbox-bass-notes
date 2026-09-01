"""Quick sanity check on a Rekordbox master.db copy.

Usage:
    .venv/bin/python -m backend.inspect_db [path-to-master.db]

Defaults to the path in backend.config.settings (sample/master.db). Reports
whether it opens, the track count, and how many tracks point at a local audio
file that actually exists (i.e. are analysable).
"""
from __future__ import annotations

import os
import sys
from collections import Counter

from pyrekordbox import Rekordbox6Database

from .config import settings

_STREAM_PREFIXES = ("apple-music:", "tidal:", "beatport:", "soundcloud:", "spotify:")


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else settings.db_path
    print(f"opening: {path}")
    db = Rekordbox6Database(path)
    rows = list(db.get_content())
    print(f"opened OK — {len(rows)} content rows\n")

    kinds: Counter[str] = Counter()
    local = []
    for c in rows:
        p = c.FolderPath or ""
        if not p:
            kinds["(empty FolderPath)"] += 1
        elif "://" in p or p.startswith(_STREAM_PREFIXES):
            kinds[p.split(":", 1)[0] + ":  (streaming)"] += 1
        elif os.path.isfile(p):
            kinds["local file — EXISTS"] += 1
            local.append(c)
        else:
            kinds["local path — MISSING"] += 1

    for k, n in kinds.most_common():
        print(f"  {n:4d}  {k}")

    print(f"\n{len(local)} analysable (local file present). First few:")
    for c in local[:5]:
        print(f"  [{c.ID}] {c.Title} — {c.ArtistName}")
        print(f"         {c.FolderPath}")

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
