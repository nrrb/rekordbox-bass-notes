"""Batch-analyse every local track and summarise per-band dBFS distributions.

Raw material for calibrating settings.dbfs_scale (the per-band dBFS endpoints).

Usage:
    python -m backend.calibrate [--limit N] [--out results.json]

Writes per-track per-band results to JSON and prints, for each band:
percentiles of the dBFS distribution, a coarse histogram, and suggested
(min, max) endpoints that would map the p5..p95 range onto digits 0..9.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from statistics import median

from .analysis import analyze_file
from .config import settings
from .db import RekordboxDB

_PCTS = (0, 5, 10, 25, 50, 75, 90, 95, 100)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return float("nan")
    if pct <= 0:
        return sorted_vals[0]
    if pct >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _histogram(vals: list[float], lo: float, hi: float, bins: int = 14) -> str:
    if not vals:
        return "(no data)"
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        idx = min(bins - 1, max(0, int((v - lo) / width)))
        counts[idx] += 1
    peak = max(counts) or 1
    out = []
    for i, c in enumerate(counts):
        edge = lo + i * width
        bar = "#" * round(40 * c / peak)
        out.append(f"    {edge:6.1f} dBFS |{bar} {c}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.calibrate")
    ap.add_argument("--limit", type=int, default=None, help="analyse at most N tracks")
    ap.add_argument("--out", default="calibration.json", help="raw results output path")
    args = ap.parse_args(argv)

    db = RekordboxDB()
    tracks = [t for t in db.list_tracks(limit=10**9) if t.has_file]
    if args.limit:
        tracks = tracks[: args.limit]
    print(f"analysing {len(tracks)} local tracks (order {settings.filter_order}, "
          f"fs {settings.audio_sr} Hz)...\n", file=sys.stderr)

    rows: list[dict] = []
    per_band: dict[str, list[float]] = {"L": [], "M": [], "H": []}
    t_start = time.time()
    for i, tr in enumerate(tracks, 1):
        try:
            res = analyze_file(tr.folder_path)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(tracks)}] !! {tr.title}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        row = {
            "id": tr.id, "title": tr.title, "artist": tr.artist,
            "genre": tr.genre, "duration_sec": round(res.duration_sec, 1),
            "token": res.token,
            "dbfs": {b.band: round(b.dbfs, 2) for b in res.bands},
            "digit": {b.band: b.digit for b in res.bands},
        }
        rows.append(row)
        for b in res.bands:
            per_band[b.band].append(b.dbfs)
        if i % 10 == 0 or i == len(tracks):
            print(f"  [{i}/{len(tracks)}] {time.time() - t_start:5.1f}s  last: {tr.title} -> {res.token}",
                  file=sys.stderr)

    with open(args.out, "w") as fh:
        json.dump(rows, fh, indent=2)
    print(f"\nwrote {len(rows)} rows -> {args.out}  ({time.time() - t_start:.1f}s total)\n", file=sys.stderr)

    # ---- summary ----
    band_names = {"L": "Low  20-39", "M": "Mid  39-77", "H": "High 77-150"}
    for band in ("L", "M", "H"):
        vals = sorted(per_band[band])
        if not vals:
            continue
        pcts = {p: _percentile(vals, p) for p in _PCTS}
        print(f"=== {band_names[band]} Hz  (n={len(vals)}) ===")
        print("  percentiles (dBFS): " + "  ".join(f"p{p}={pcts[p]:.1f}" for p in _PCTS))
        print(f"  mean={sum(vals) / len(vals):.1f}  median={median(vals):.1f}  spread(p5..p95)={pcts[95] - pcts[5]:.1f} dB")
        print(_histogram(vals, pcts[0], pcts[100]))
        # suggest endpoints: map p5..p95 onto 0..9 (a touch of head/tail room)
        sug_lo = round(pcts[5])
        sug_hi = round(pcts[95])
        print(f"  suggested dbfs_scale[{band!r}] = ({sug_lo}, {sug_hi})\n")

    # digit distribution under the CURRENT per-band scale
    print("--- digit spread under current per-band dbfs_scale ---")
    for band in ("L", "M", "H"):
        lo, hi = settings.dbfs_scale[band]
        hist = [0] * 10
        for r in rows:
            hist[r["digit"][band]] += 1
        print(f"  {band} [{lo:+.0f}..{hi:+.0f} dBFS]: " + " ".join(f"{d}:{hist[d]:>3}" for d in range(10)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
