"""Sub-bass profile analysis.

Given an audio file, measure the energy in three log-spaced sub-bands of the
20-150 Hz range and encode each as a 0-9 digit on a *fixed* dBFS scale,
producing a token like ``B:l5m7h9``:

    B:      fixed preset prefix (``settings.preset_letter``)
    l/m/h   Low / Medium / High sub-band (lowercased so the digits stand out)
    digit   0-9, where ``d`` means "d0-d9 % strength"; per band the scale maps
            ``settings.dbfs_scale[band]`` -> (min dBFS -> 0, max dBFS -> 9).
            Absolute (referenced to full scale), so digits are comparable
            across any tracks; frozen once written (recalibrate => bump preset).

Method (see PLAN.md, "Locked-in decisions"):

    1. decode -> mono, resample to ``settings.audio_sr`` (default 500 Hz).
    2. per band: zero-phase Butterworth band-pass (``settings.filter_order``,
       second-order sections) via ``sosfiltfilt``, then RMS over the whole
       track.
    3. RMS -> dBFS (0 dBFS = full-scale sine, AES-17) -> digit.

The per-band dBFS endpoints in ``settings.dbfs_scale`` were calibrated from a
117-track sample (see backend/calibrate.py).

CLI::

    python -m backend.analysis TARGET [TARGET ...] [--json] [--sr N] [--comment TEXT]

Each TARGET is an audio file path or a Rekordbox track ID (resolved via the
configured database).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy import signal

from .config import settings

# RMS of a full-scale sine (amplitude 1.0), defined as 0 dBFS (AES-17).
_DBFS_REF_RMS = 1.0 / math.sqrt(2.0)
_TINY = 1e-12
_BAND_LABELS = ("L", "M", "H")


# --------------------------------------------------------------------------- data
@dataclass
class BandResult:
    band: str  # "L" | "M" | "H"
    hz_low: float
    hz_high: float
    rms: float
    dbfs: float
    digit: int


@dataclass
class AnalysisResult:
    path: str
    sample_rate: int
    duration_sec: float
    n_samples: int
    bands: list[BandResult]
    token: str

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class MergeResult:
    comment: str  # the new comment text
    action: str  # "replaced" (a token was already present) | "prepended"
    existing_tokens: int  # how many existing tokens were found and removed


# ----------------------------------------------------------------------- helpers
def log_band_edges(lo: float, hi: float, n: int) -> list[float]:
    """``n`` log-spaced bands between ``lo`` and ``hi`` -> ``n + 1`` edges."""
    ratio = hi / lo
    return [lo * ratio ** (k / n) for k in range(n + 1)]


def _band_edges() -> list[float]:
    edges = [float(x) for x in settings.band_edges_hz]
    if len(edges) != 4:
        raise ValueError(f"expected 4 band edges, got {edges!r}")
    if not all(a < b for a, b in zip(edges, edges[1:])):
        raise ValueError(f"band edges must be strictly increasing: {edges!r}")
    return edges


def _design_bandpass(lo: float, hi: float, fs: int, order: int) -> np.ndarray:
    nyq = fs / 2.0
    if not 0.0 < lo < hi < nyq:
        raise ValueError(
            f"band {lo}-{hi} Hz invalid for fs={fs} Hz (Nyquist {nyq}); "
            f"raise settings.audio_sr"
        )
    sos = signal.butter(order, [lo / nyq, hi / nyq], btype="band", output="sos")
    # stability / conditioning guard: every pole strictly inside the unit circle
    _, poles, _ = signal.sos2zpk(sos)
    max_pole = float(np.max(np.abs(poles))) if len(poles) else 0.0
    if max_pole >= 0.999:
        raise RuntimeError(
            f"ill-conditioned band-pass for {lo}-{hi} Hz at fs={fs} Hz "
            f"(max |pole| = {max_pole:.5f}); lower settings.filter_order or "
            f"raise settings.audio_sr"
        )
    return sos


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def _to_dbfs(rms: float) -> float:
    return 20.0 * math.log10(max(rms, _TINY) / _DBFS_REF_RMS)


def _digit(dbfs: float, band: str) -> int:
    lo, hi = settings.dbfs_scale[band]
    frac = (dbfs - lo) / (hi - lo)  # 0..1 across this band's fixed absolute scale
    return int(min(9, max(0, math.floor(frac * 10.0))))


# ------------------------------------------------------------------------ core
def load_audio(path: str, sr: Optional[int] = None) -> tuple[np.ndarray, int]:
    """Decode ``path`` to mono float64 at ``sr`` (default ``settings.audio_sr``).

    Note: on Python 3.11-3.12 librosa's ``audioread`` fallback prints a few
    ``DeprecationWarning`` lines (aifc/audioop/sunau) to stderr on first decode.
    Harmless and unsuppressable from here (the import path resets warning
    filters); gone once on Python 3.13+ where those stdlib modules are removed
    and librosa uses soundfile/ffmpeg directly.
    """
    import librosa  # deferred: heavy import (numba warm-up)

    target = settings.audio_sr if sr is None else sr
    y, out_sr = librosa.load(
        path, sr=target, mono=True, res_type=settings.audio_res_type
    )
    return np.asarray(y, dtype=np.float64), int(out_sr)


def analyze_samples(y: np.ndarray, fs: int) -> AnalysisResult:
    """Analyse an already-decoded mono signal."""
    edges = _band_edges()
    order = settings.filter_order
    bands: list[BandResult] = []
    for label, lo, hi in zip(_BAND_LABELS, edges[:-1], edges[1:]):
        sos = _design_bandpass(lo, hi, fs, order)
        y_band = signal.sosfiltfilt(sos, y)
        rms = _rms(y_band)
        dbfs = _to_dbfs(rms)
        bands.append(BandResult(label, lo, hi, rms, dbfs, _digit(dbfs, label)))

    # band letters lowercased in the token so the digits stand out: "B:l6m9h7"
    token = settings.preset_letter + ":" + "".join(f"{b.band.lower()}{b.digit}" for b in bands)
    return AnalysisResult(
        path="",
        sample_rate=fs,
        duration_sec=(len(y) / fs) if fs else 0.0,
        n_samples=len(y),
        bands=bands,
        token=token,
    )


def analyze_file(path: str, sr: Optional[int] = None) -> AnalysisResult:
    y, fs = load_audio(path, sr=sr)
    res = analyze_samples(y, fs)
    res.path = path
    return res


# ------------------------------------------------------------------ token merge
def _token_pattern() -> re.Pattern[str]:
    # band letters match either case so tokens written before the lowercase
    # switch are still recognised; the preset letter stays case-sensitive.
    return re.compile(re.escape(settings.preset_letter) + r":[Ll]\d[Mm]\d[Hh]\d")


def merge_token(comment: Optional[str], token: str) -> MergeResult:
    """Put ``token`` at the FRONT of ``comment``.

    Every existing ``<preset>:l#m#h#`` token (either letter case) is removed
    first, then ``token`` is prepended before the remaining text (joined with
    ``settings.comment_sep``). The rest of the comment is preserved; whitespace
    left where tokens were removed is collapsed. ``existing_tokens`` is how many
    were found and removed.
    """
    text = comment or ""
    pat = _token_pattern()
    matches = pat.findall(text)
    rest = re.sub(r"\s{2,}", " ", pat.sub("", text)).strip()
    new = f"{token}{settings.comment_sep}{rest}" if rest else token
    return MergeResult(new, "replaced" if matches else "prepended", len(matches))


# -------------------------------------------------------------------------- CLI
def _resolve_targets(targets: Sequence[str]) -> list[tuple[str, str]]:
    """Map CLI targets (file paths or track IDs) to (label, path) pairs."""
    out: list[tuple[str, str]] = []
    db = None
    for t in targets:
        if os.path.isfile(t):
            out.append((t, t))
            continue
        if db is None:
            from .db import RekordboxDB  # deferred: only needed for ID lookups

            db = RekordboxDB()
        track = db.get_track(t)
        if track is None:
            print(f"!! {t!r}: not a file and not a known track ID", file=sys.stderr)
        elif not track.has_file:
            print(
                f"!! track {t} ({track.title}) has no local file: "
                f"{track.folder_path or '(empty)'}",
                file=sys.stderr,
            )
        else:
            out.append((f"[{track.id}] {track.title} - {track.artist}", track.folder_path))
    return out


def _print_human(label: str, res: AnalysisResult) -> None:
    print(label)
    print(
        f"  {res.duration_sec:7.1f}s   {res.sample_rate} Hz   "
        f"{res.n_samples} samples   order {settings.filter_order}"
    )
    print(f"  band   {'range (Hz)':>13}   {'RMS':>10}   {'dBFS':>7}   digit")
    for b in res.bands:
        print(
            f"  {b.band:<5}  {b.hz_low:6.1f}-{b.hz_high:6.1f}   "
            f"{b.rms:10.6f}   {b.dbfs:7.1f}   {b.digit}"
        )
    print(f"  token: {res.token}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m backend.analysis",
        description="Sub-bass profile analysis -> B:L#M#H# token.",
    )
    ap.add_argument("targets", nargs="+", help="audio file path(s) or Rekordbox track ID(s)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--sr", type=int, default=None, help="override analysis sample rate (Hz)")
    ap.add_argument(
        "--comment",
        default=None,
        help="preview merging the token into this existing comment (single target)",
    )
    args = ap.parse_args(argv)

    resolved = _resolve_targets(args.targets)
    if not resolved:
        print("no analysable targets", file=sys.stderr)
        return 2

    results = []
    for label, path in resolved:
        try:
            res = analyze_file(path, sr=args.sr)
        except Exception as e:  # noqa: BLE001 - CLI: report and continue
            print(f"!! {label}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        results.append((label, res))
        if not args.json:
            _print_human(label, res)
            if args.comment is not None:
                m = merge_token(args.comment, res.token)
                dup = f"  (warning: {m.existing_tokens} existing tokens)" if m.existing_tokens > 1 else ""
                print(f"  merge ({m.action}): {m.comment!r}{dup}")
            print()

    if args.json:
        payload = [dict(label=label, **res.as_dict()) for label, res in results]
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
