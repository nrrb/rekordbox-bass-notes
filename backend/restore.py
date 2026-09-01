"""List and restore master.db backups written by the comment write-path.

    python -m backend.restore                     list backups + what's in them
    python -m backend.restore <index>             restore backup N from the list
    python -m backend.restore <name-substring>    restore the backup matching a name
    python -m backend.restore <target> --yes      skip the confirmation prompt
    python -m backend.restore --dir PATH ...       use a different backup dir

Restoring first snapshots the current live database (``*_prerestore.db``), so a
restore is itself reversible, then copies the chosen backup over the live
master.db and removes the live -wal/-shm sidecars (a stale WAL against the
restored file would silently revert it).

Run this with the backend server stopped and Rekordbox closed.
"""
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from .config import settings
from .db import RekordboxDB, RekordboxRunningError, rekordbox_running

_TS_FMT = RekordboxDB.BACKUP_TS_FMT


@dataclass
class BackupInfo:
    path: Path
    taken: Optional[datetime]
    size: int
    wal_size: int
    shm_size: int
    usn: Optional[int] = None
    track_count: Optional[int] = None
    tagged_count: Optional[int] = None
    recent: list[tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _ago(dt: datetime) -> str:
    s = (datetime.now() - dt).total_seconds()
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{s / 60:.0f} min ago"
    if s < 172800:
        return f"{s / 3600:.0f} h ago"
    return f"{s / 86400:.0f} days ago"


def _parse_taken(path: Path, live_stem: str) -> Optional[datetime]:
    stamp = path.stem[len(live_stem) + 1:]  # drop "<stem>_"
    stamp = stamp.replace("_prerestore", "")
    try:
        return datetime.strptime(stamp, _TS_FMT)  # naive local, matches db.backup()
    except ValueError:
        return None


def _inspect(path: Path) -> tuple[Optional[int], Optional[int], Optional[int], list, Optional[str]]:
    """Open a backup read-only-ish and pull identifying info. Best-effort."""
    pre_sidecars = {
        s: (path.parent / (path.name + s)).exists() for s in ("-wal", "-shm")
    }
    db = None
    try:
        db = RekordboxDB(str(path))
        sess = db._db.session
        usn = sess.execute(
            text("SELECT int_1 FROM agentRegistry WHERE registry_id='localUpdateCount'")
        ).scalar()
        total = sess.execute(text("SELECT COUNT(*) FROM djmdContent")).scalar()
        glob = f"*{settings.preset_letter}:[Ll][0-9][Mm][0-9][Hh][0-9]*"
        tagged = sess.execute(
            text("SELECT COUNT(*) FROM djmdContent WHERE Commnt GLOB :g"), {"g": glob}
        ).scalar()
        recent = sess.execute(
            text(
                "SELECT Title, updated_at FROM djmdContent "
                "WHERE updated_at IS NOT NULL ORDER BY updated_at DESC LIMIT 3"
            )
        ).fetchall()
        return usn, total, tagged, [(t or "(untitled)", u or "") for t, u in recent], None
    except Exception as e:  # noqa: BLE001
        return None, None, None, [], f"{type(e).__name__}: {e}"
    finally:
        if db is not None:
            db.close()
        # remove sidecars our read created (empty -wal, coordination -shm)
        for s, existed in pre_sidecars.items():
            side = path.parent / (path.name + s)
            if not existed and side.exists():
                side.unlink(missing_ok=True)


def list_backups(backup_dir: Optional[Path] = None, live_stem: str = "master") -> list[BackupInfo]:
    out_dir = Path(backup_dir or settings.backup_dir)
    if not out_dir.is_dir():
        return []
    infos: list[BackupInfo] = []
    for main in out_dir.glob(f"{live_stem}_*.db"):
        wal = out_dir / (main.name + "-wal")
        shm = out_dir / (main.name + "-shm")
        info = BackupInfo(
            path=main,
            taken=_parse_taken(main, live_stem),
            size=main.stat().st_size,
            wal_size=wal.stat().st_size if wal.exists() else 0,
            shm_size=shm.stat().st_size if shm.exists() else 0,
        )
        info.usn, info.track_count, info.tagged_count, info.recent, info.error = _inspect(main)
        infos.append(info)
    infos.sort(key=lambda i: (i.taken or datetime.min), reverse=True)
    return infos


def _print_listing(infos: list[BackupInfo], live: Path) -> None:
    print(f"live database: {live}")
    try:
        cur = RekordboxDB(str(live))
        sess = cur._db.session
        usn = sess.execute(
            text("SELECT int_1 FROM agentRegistry WHERE registry_id='localUpdateCount'")
        ).scalar()
        total = sess.execute(text("SELECT COUNT(*) FROM djmdContent")).scalar()
        glob = f"*{settings.preset_letter}:[Ll][0-9][Mm][0-9][Hh][0-9]*"
        tagged = sess.execute(
            text("SELECT COUNT(*) FROM djmdContent WHERE Commnt GLOB :g"), {"g": glob}
        ).scalar()
        cur.close()
        print(f"  usn {usn}   {total} tracks   {tagged} tagged\n")
    except Exception as e:  # noqa: BLE001
        print(f"  (could not read live db: {e})\n")

    if not infos:
        print("no backups found in", settings.backup_dir)
        return

    for n, i in enumerate(infos, 1):
        when = (
            f"{i.taken:%Y-%m-%d %H:%M:%S}  ({_ago(i.taken)})"
            if i.taken
            else "unknown time"
        )
        pre = "  [pre-restore snapshot]" if "_prerestore" in i.path.name else ""
        print(f"[{n:2}] {i.path.name}{pre}")
        print(f"     taken   {when}")
        sidecars = []
        if i.wal_size:
            sidecars.append(f"-wal {_fmt_size(i.wal_size)}")
        if i.shm_size:
            sidecars.append(f"-shm {_fmt_size(i.shm_size)}")
        extra = f"  (+ {', '.join(sidecars)})" if sidecars else ""
        print(f"     size    {_fmt_size(i.size)}{extra}")
        if i.error:
            print(f"     !! could not read contents: {i.error}")
        else:
            print(f"     usn     {i.usn}   {i.track_count} tracks   {i.tagged_count} tagged")
            if i.recent:
                print("     recent edits:")
                for title, updated in i.recent:
                    print(f"       {updated[:19]:19}  {title}")
        print()
    print("restore:  python -m backend.restore <index|name>")


def _resolve(target: str, infos: list[BackupInfo]) -> BackupInfo:
    if target.isdigit():
        idx = int(target)
        if not 1 <= idx <= len(infos):
            raise SystemExit(f"index {idx} out of range (1..{len(infos)})")
        return infos[idx - 1]
    matches = [i for i in infos if target in i.path.name]
    if not matches:
        raise SystemExit(f"no backup name contains {target!r}")
    if len(matches) > 1:
        raise SystemExit(
            f"{target!r} matches {len(matches)} backups; be more specific:\n  "
            + "\n  ".join(m.path.name for m in matches)
        )
    return matches[0]


def _snapshot_live(live: Path, backup_dir: Path) -> Path:
    ts = datetime.now().strftime(_TS_FMT)
    dest = backup_dir / f"{live.stem}_{ts}_prerestore{live.suffix}"
    shutil.copy2(live, dest)
    for s in ("-wal", "-shm"):
        side = live.with_name(live.name + s)
        if side.exists():
            shutil.copy2(side, dest.with_name(dest.name + s))
    return dest


def restore(target: str, assume_yes: bool = False, backup_dir: Optional[Path] = None) -> int:
    out_dir = Path(backup_dir or settings.backup_dir)
    infos = list_backups(out_dir)
    if not infos:
        raise SystemExit(f"no backups in {out_dir}")
    chosen = _resolve(target, infos)

    cur = RekordboxDB()
    live = cur.db_path
    cur.close()

    if rekordbox_running():
        raise SystemExit("Rekordbox is running — quit it before restoring.")

    print("!! Stop the backend server (uvicorn) before continuing if it is running.\n")
    taken = f"{chosen.taken:%Y-%m-%d %H:%M:%S}" if chosen.taken else "unknown time"
    print(f"restore   {chosen.path.name}")
    print(f"          (taken {taken}; usn {chosen.usn}, {chosen.tagged_count} tagged)")
    print(f"     over {live}")
    if not assume_yes:
        if input("\nType 'restore' to proceed: ").strip().lower() != "restore":
            raise SystemExit("aborted")

    pre = _snapshot_live(live, out_dir)
    print(f"\ncurrent db snapshotted -> {pre.name}")

    shutil.copy2(chosen.path, live)
    for s in ("-wal", "-shm"):
        live.with_name(live.name + s).unlink(missing_ok=True)

    print(f"restored. {live}\n          now holds the contents of {chosen.path.name}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.restore", description=__doc__.split("\n\n")[0])
    ap.add_argument("target", nargs="?", help="backup index (from the list) or a name substring")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--dir", default=None, help="backup directory (default: settings.backup_dir)")
    args = ap.parse_args(argv)

    backup_dir = Path(args.dir) if args.dir else None
    if args.target is None:
        try:
            cur = RekordboxDB()
            live = cur.db_path
            cur.close()
        except Exception:  # noqa: BLE001
            live = Path(settings.db_path or "master.db")
        _print_listing(list_backups(backup_dir), live)
        return 0
    return restore(args.target, assume_yes=args.yes, backup_dir=backup_dir)


if __name__ == "__main__":
    raise SystemExit(main())
