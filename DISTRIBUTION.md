# Distribution Plan — rekordbox bass notes for macOS

Turning the POC into a tool a handful of DJ friends can install and use on their
own Macs, against their own Rekordbox libraries.

See [`PLAN.md`](PLAN.md) for the app itself and [`README.md`](README.md) for dev
setup. This document is only about packaging and shipping.

---

## Phase 0 — parallel-safe prep — ✅ complete

Backend-only / additive hardening done **without disturbing the `npm run dev` +
`uvicorn --reload` loop**, so UI tweaking could continue alongside. Decisions
locked: app name **rekordbox bass notes**; **soundfile-only** decoding for now
(M4A/AAC/ALAC → a clear "not supported yet" error, `ffmpeg` in M4); **both**
backup endpoints added.

| # | Item | Touches | Status |
|---|------|---------|--------|
| 0.1 | **Drop librosa** → `soundfile` decode + `scipy.signal.resample_poly` to `AUDIO_SR`. Removed `audio_res_type`. Re-ran `calibrate.py`: 1 of ~117 tracks shifts one digit at a boundary → **`dbfs_scale` unchanged, `PRESET_LETTER=B`**. `AudioDecodeError` for unsupported/corrupt; M4A/AAC/ALAC → "not supported yet". audioread `DeprecationWarning` noise gone. | `analysis.py`, `config.py`, `requirements.txt` | ✅ |
| 0.2 | **Runtime config** — `backend/runtime.py`: `RuntimeConfig {db_path, backup_dir}` persisted to JSON (`~/Library/Application Support/rekordbox bass notes/config.json` frozen, `./.rkbx-config.json` gitignored in dev). Precedence env → file → default; **default db_path = "" (auto-locate the real library)**. `/api/db/switch` writes it (sticky across restart — verified). `db.backup()` / `_prune_backups` / `restore.py` read `backup_dir` from it. | `runtime.py` (new), `db.py`, `restore.py`, `main.py` | ✅ |
| 0.3 | **Human error messages** — `humanize()` / `_http()` in `main.py`: library-not-found, Rekordbox open, audio moved, decode/format failure, unsupported-DB-version → plain sentences in `detail`, applied to the analyze / batch-stream / write / switch paths. No UI change. Verified. | `main.py` | ✅ |
| 0.4 | **Backup endpoints** — `GET /api/backups` (listing + `RekordboxDB.stats()` for the live DB) and `POST /api/backups/{name}/restore` (409 if Rekordbox open → snapshot → `restore.apply_restore` → reopen, behind `_swap_lock`). `restore.py` refactored: `resolve_backup()` (raises, no `SystemExit`) + `apply_restore()` shared with the CLI. Full HTTP round-trip not run (Rekordbox was open — guard verified; mechanics covered by the CLI). Restore **panel** is UI work. | `main.py`, `restore.py`, `db.py` | ✅ |
| 0.5 | **Additive static mount** — `app.mount("/", StaticFiles(frontend/dist, html=True))` last, only when `frontend/dist/index.html` exists (`sys._MEIPASS`-aware). Verified: skipped in dev; serves the SPA at `/` with `/api/*` still winning when a build is present. **`npm run dev` unaffected.** | `main.py` | ✅ |
| 0.6 | Doc sync — PLAN.md + README (librosa/ffmpeg, `runtime.py`, `humanize`, `/api/backups`, `/api/db/switch` persistence, `config.json` precedence). | `PLAN.md`, `README.md` | ✅ |

Also since done, outside the numbered list: the `sample/master.db` and every code
reference to it were removed — the app now defaults to the real library.

---

## Current state (dev)

Runs as two dev processes (`uvicorn --reload` + `npm run dev`). Already built
toward distribution:

- **Real library by default** — auto-located via `pyrekordbox`, no sample DB.
  Header badge `MY LIBRARY` / `CUSTOM DATABASE`; **use a different database…**
  opens another `master.db` (path field), persisted to `config.json`.
- **Single-user safe** — every DB call serialised on a re-entrant lock + a
  session rollback before each write (fixes a threadpool "write doesn't persist"
  bug found via the batch flow).
- **Writes** — `PUT /api/tracks/{id}/comment` and atomic batch
  `PUT /api/tracks/comments`; pre-write backup (+ `-wal`/`-shm`), `BACKUP_KEEP`
  retention, post-write `PRAGMA quick_check`, two independent Rekordbox-running
  guards, rollback on failure.
- **Analysis** — `soundfile` + `scipy.signal.resample_poly` (librosa gone).
  `POST /api/tracks/{id}/analyze` and streamed batch `POST /api/tracks/analyze`
  (NDJSON, one line per track, same shape as single). M4A/AAC/ALAC → clear
  "not supported yet".
- **Analysis cache** — results kept per track id for the current library
  (`analysisCache.tsx`), cleared on DB switch / restore. Deselect and reselect a
  track and its result is still there; single ↔ batch share results both ways;
  the batch flow only re-fetches tracks not already cached.
- **Backups API** — `GET /api/backups` (listing + live-DB stats),
  `POST /api/backups/{name}/restore` (guarded, snapshots current DB first). CLI
  `python -m backend.restore` shares the same code.
- **Audio player** — `GET /api/tracks/{id}/audio` (Range-enabled `FileResponse`);
  a ▶ button per row and an always-visible `PlayerPanel` (play/pause, seek,
  Web Audio spectrum analyser). The analyser uses a log frequency axis with the
  first three bars pinned to the colour-coded L / M / H sub-bass bands (`fftSize
  4096` for ~10 Hz resolution). The draw loop reads the `AnalyserNode` through a
  ref, so it attaches on the first play of a fresh load (earlier it needed a
  page refresh).
- **Human errors** — `humanize()` maps the common failures to plain `detail`
  sentences.
- **Layout** — two-column workspace: track list 70%, sticky detail column 30%
  (player + analysis panels), stacks under 860 px.
- **One-process ready** — FastAPI serves `frontend/dist` at `/` when a build is
  present (skipped in dev); CORS opens to `*` when `sys.frozen`.
- **Runtime config** — `backend/runtime.py`: `db_path` + `backup_dir` persisted;
  precedence env → `config.json` → default. `__version__` in `/api/health`.
- **Resilient UI** — starts even with no database (`NoLibrary` locate screen);
  a **Backups** panel (list + inline restore); a persistent **Rekordbox-running
  banner**; `/api/health` **polled every 5 s** so opening Rekordbox mid-session
  is noticed; version in the footer.

### Known rough edges

- The player has only been exercised in dev (Chrome via the Vite proxy); Range
  playback and Web Audio behaviour in the packaged pywebview (WebKit) shell are
  untested.
- The packaged `.app` has only been run **headless** (`RKBX_NO_WINDOW=1`) so far
  — the pywebview window, the native file dialog, and `open-external` still need
  a real GUI pass.

---

## Phase 1 — packaging build-out — 🟡 mostly done

Added since Phase 0 (see the per-item ✅s below for detail):

- `launcher.py` — the frozen entry point (uvicorn thread + pywebview window +
  single-instance lock + graceful shutdown).
- `backend/logging_setup.py` — rotating file log; `GET /api/diagnostics` +
  footer **Copy diagnostics**.
- `backend/update_check.py` — `GET /api/update-check` vs GitHub Releases;
  `UpdateBanner`; `last_seen_version` persisted.
- `backend/desktop.py` + `POST /api/pick-file` + `BrowseButton` — native
  "choose your master.db" dialog (packaged only), text field otherwise.
- ffmpeg fallback decode in `backend/analysis.py` (M4A/AAC/ALAC/MP4/WMA).
- `requirements.txt` pinned; `pywebview` + `imageio-ffmpeg` added.
- `db.rekordbox_running()` tightened to an exact process-name match (was a
  prefix match that flagged the packaged app itself); new advisory
  `db.rekordbox_agent_running()`; frozen exe renamed `bass-notes`;
  `backend/tests/test_process_detection.py`.
- `rekordbox bass notes.spec`, `scripts/build_app.sh`, `scripts/make_icns.sh`,
  `packaging/icon.icns` — an arm64 build succeeds and passes a headless smoke
  test (opens the real encrypted library, serves the SPA, analyses an MP3).

Still open: a GUI-window pass, `.dmg` polish, RB v5 path check, clean-machine
field test, signing.

---

## Goal

- A double-clickable macOS app. No Terminal, no `pip`, no Homebrew.
- Works on a clean Mac with only Rekordbox installed.
- Finds the user's real library automatically; backs up before every write;
  offers restore.
- Distributed privately to ~5–20 known people, updated from one place.

## Target artifact

| | v1 (first share) | v2 (if it sticks) |
|---|---|---|
| Form | `.app` inside a `.dmg` | same |
| Signing | unsigned (right-click → Open once) | Developer ID signed **+ notarized** |
| Arch | `arm64` (build a separate `x86_64` only if a friend needs it) | same, possibly `universal2` |
| Channel | private GitHub Releases | same |
| Update | in-app "new version available" banner → link | same, or Sparkle after signing |

## Non-goals

- App Store (sandboxing blocks `~/Library/Pioneer/…` without security-scoped
  bookmarks — not worth it).
- Homebrew tap, Electron, cross-platform. Windows/Linux are separate efforts if
  ever wanted.
- Public listing — the bundled key-derivation (via `pyrekordbox`) is a licensing
  gray area; keep it a private share.

---

## What's left for a shippable v1

Each subsection is flagged: ✅ done · 🟡 partly done · ⬜ not started.

### 1. One process — ✅

- ✅ FastAPI serves `frontend/dist` at `/` (`sys._MEIPASS`-aware), `/api/*` first,
  skipped when no build is present.
- ✅ CORS relaxed to `*` when `sys.frozen` (same-origin in the packaged app).
- ✅ SPA built into the bundle — the spec adds `frontend/dist`; a frozen arm64
  build was verified serving `/` and `/api/*` from one process.

### 2. Launcher — ✅

`launcher.py` (PyInstaller entry point):
  1. ✅ file logging via `backend/logging_setup.py`; single-instance lock
     (`fcntl.flock` on `…/Application Support/rekordbox bass notes/app.lock`).
  2. ✅ picks a free `127.0.0.1` port (pre-bind → read back → hand to uvicorn).
  3. ✅ uvicorn runs in a daemon thread; `wait_until_ready()` polls `/api/health`.
  4. ✅ **pywebview** window at `http://127.0.0.1:<port>`; `webbrowser.open`
     fallback if no GUI backend. `RKBX_NO_WINDOW=1` runs it headless (smoke tests).
  5. ✅ window close → `server.should_exit` → join → exit; lock released on exit.

### 3. Dependency slimming — ✅

- ✅ **librosa dropped** (→ numba → llvmlite, ~300–400 MB): decode is
  `soundfile`/libsndfile (WAV/AIFF/FLAC/MP3/OGG), resample is
  `scipy.signal.resample_poly`. Recalibration: 1/117 tracks shifted one digit at
  a boundary → `dbfs_scale` / `PRESET_LETTER` unchanged.
- ✅ **`ffmpeg` for M4A/AAC/ALAC** — `imageio-ffmpeg`'s bundled binary; anything
  libsndfile rejects is retried through `ffmpeg -f f32le` in
  `backend/analysis.py::_decode_via_ffmpeg` (ffmpeg does the resample). WAV vs
  AAC/ALAC of the same tone agree to the digit. "not supported yet" error gone.
- ✅ **`requirements.txt` pinned** to the built venv (numpy 2.4.6, scipy 1.17.1,
  soundfile 0.14.0, fastapi 0.141.1, uvicorn 0.52.4, psutil 7.2.2, +
  `imageio-ffmpeg==0.6.0`, `pywebview==6.2.1`).

Runtime deps: `numpy`, `scipy`, `soundfile`, `pyrekordbox` (**pinned `==0.4.4`**),
`sqlcipher3-wheels`, `fastapi`, `uvicorn`, `psutil`, `pywebview`, `imageio-ffmpeg`.

### 4. Config & writable paths — ✅

- ✅ `backend/runtime.py` — `db_path` + `backup_dir` persisted to
  `config.json` (`~/Library/Application Support/rekordbox bass notes/` frozen,
  `./.rkbx-config.json` in dev). Precedence env → file → default. `/api/db/switch`
  and the restore endpoint write it.
- ✅ Backups default to **`~/Music/rekordbox bass notes Backups/`** when frozen
  (`backend/backups/` in dev).
- ✅ `backend/__init__.py` `__version__` — in `/api/health` and the UI footer.
- ✅ **File logging** — `backend/logging_setup.py`: rotating `app.log`
  (`~/Library/Logs/rekordbox bass notes/` frozen, `./.logs/` dev), uvicorn
  records fold in. `GET /api/diagnostics` returns the tail; footer **Copy
  diagnostics** button copies it. `log_path` is in `/api/health`.
- ✅ `last_seen_version` in `config.json` — set by `POST /api/update-check/dismiss`.

### 5. First-run library setup — 🟡

- ✅ Auto-locates the library; `humanize()` turns "not found" into a plain
  message; the backend **starts even with no DB** (`_state["db"] = None`), health
  returns `db_kind: "none"` / `db_path: null`, DB-needing endpoints → 503.
- ✅ **`NoLibrary` screen** — when `db_kind === "none"` the app shows a
  locate-your-`master.db` panel (detected-path "Open it", a path field, and
  "Retry auto-detect") instead of a broken table.
- 🟡 **Native file dialog** — bridge done: `launcher.py` registers a pywebview
  `create_file_dialog` picker into `backend/desktop.py`; `POST /api/pick-file`
  exposes it (501 in dev/browser); a self-hiding **`BrowseButton`** sits next to
  the path fields in `NoLibrary` and `DbSwitcher`. Not yet clicked in a real
  packaged window.
- ⬜ Confirm the v5 / v6 / v7 directory variants all resolve (pyrekordbox
  handles 6/7; check 5).

### 6. Restore in the UI — ✅

- `GET /api/backups` (listing + live-DB stats) and `POST /api/backups/{name}/restore`
  (guarded: 503 no DB / 409 Rekordbox open; snapshots first, reopens).
- **`RestorePanel`** — a "Backups" toggle in the toolbar; each row shows name,
  time, size, USN, track/tagged counts and the last edit, with an inline
  "restore this → Confirm restore" (disabled while Rekordbox runs). Success shows
  the pre-restore snapshot name and refreshes the library.

### 7. Error surfacing — ✅

`humanize()` in `main.py` maps library-not-found, Rekordbox-open, audio-moved,
decode/format failure, and unsupported-DB-version to plain sentences in the API
`detail`; applied to analyze, batch-stream (per track), both write paths, the DB
switch, and restore. Frontend renders `detail` as-is. (Raw detail → logs once §4
logging lands.)

### 8. Rekordbox-running UX — ✅

- `useHealth` **polls `/api/health` every 5 s**, so opening Rekordbox after the
  app is already running is picked up (and closing it re-enables Save).
- **`RekordboxBanner`** — a persistent amber banner while Rekordbox runs, with an
  "I've quit it — re-check" button (also forces a health refresh).
- **Process detection is exact-match.** `db.rekordbox_running()` matches a
  process named exactly `rekordbox` (`.exe` stripped) — same as pyrekordbox's
  own `commit()` guard, so the two never disagree. A prefix match would flag the
  packaged app's *own* process and block every write; regression-tested in
  `backend/tests/test_process_detection.py`, and the frozen Mach-O is named
  `bass-notes` (not `rekordbox bass notes`) as a second line of defence.
- **`rekordbox_agent_running`** (in `/api/health`) — advisory only. When the
  `rekordboxAgent` cloud-sync helper is up but Rekordbox itself is closed, the
  header shows a "pause sync before saving" note; it does **not** block writes
  (the agent doesn't hold the master.db write lock).

### 9. App polish — ✅ (icon is a placeholder)

- ✅ **About / version** — `__version__` in `/api/health` + a UI footer.
- ✅ **Window title** — the SPA `<title>`; `Info.plist` `CFBundleName` set in the
  spec.
- ✅ **Icon** — `packaging/icon.icns`, generated by `scripts/make_icns.sh` from
  `packaging/icon-src.svg` (the app's own bass-bolt mark on a dark rounded rect,
  rendered via QuickLook → `sips`/`iconutil`). Functional placeholder; swap the
  source SVG for a real design and re-run the script.

### 10. In-app update check — ✅ (needs a repo configured)

- ✅ `backend/update_check.py` — `GET /api/update-check` compares `__version__`
  to the latest **GitHub Releases** tag for `$UPDATE_REPO` (memoised ~1 h;
  `$UPDATE_GITHUB_TOKEN` for a private repo). `supported:false` when unset.
- ✅ **`UpdateBanner`** — dismissible "vX.Y.Z is available" with a Download button
  that opens the release page via `POST /api/open-external` (`webbrowser.open`,
  so it works from the WebKit shell). Dismiss persists `last_seen_version`.

---

## Build pipeline

### PyInstaller spec

`rekordbox bass notes.spec` is the real thing (checked in). It reads the version
from `backend/__init__.py`, refuses to build if `frontend/dist/index.html` is
missing, `collect_all`s `pyrekordbox` / `soundfile` / `imageio_ffmpeg` /
`scipy` / `numpy`, `collect_dynamic_libs` for `sqlcipher3`, adds the uvicorn
protocol/lifespan hidden imports, and emits a `.app` with the icon + an
`Info.plist` (`CFBundleName`, version, `LSMinimumSystemVersion 12.0`,
`NSAllowsLocalNetworking`). The Mach-O executable is named **`bass-notes`**
(`EXE_NAME`), not `rekordbox bass notes`, so the running process can't be
confused with Rekordbox by a name match; `CFBundleName` and the window title are
unchanged.

```
.venv/bin/pyinstaller "rekordbox bass notes.spec" --noconfirm
```

**Status:** a full `--target-arch arm64` build succeeds and was smoke-tested
headless (`RKBX_NO_WINDOW=1`): opens the real encrypted `master.db` (sqlcipher3 +
pyrekordbox key blob resolve frozen), serves the SPA at `/`, and analyses a real
MP3 end-to-end (`B:l3m9h7`). Bundle ~213 MB. Not yet run through a GUI window,
`create-dmg`, or signing.

Known gotchas for this stack:

- **`sqlcipher3-wheels`** — the compiled `_sqlite3*.so` (SQLCipher + OpenSSL
  statically linked) is imported dynamically by `pyrekordbox`; needs
  `--collect-binaries` or it's missing at runtime.
- **`pyrekordbox`** — bundles the deobfuscated key blob (offline, good) and a
  `config` module that reads plists; `--collect-all`.
- **`imageio_ffmpeg`** — ships the `ffmpeg` binary inside the package; ensure it's
  collected and stays `+x` after extraction.
- **`soundfile`** — bundles `libsndfile` in `_soundfile_data/`; `--collect-all`.
  Confirm the wheel's libsndfile ≥ 1.1 if relying on native MP3.
- **uvicorn** — protocol/lifespan modules are late-imported → hidden imports.
- **numpy / scipy** — official hooks exist; still `--collect-all` and watch total
  size and the `scipy.special` cython bits.
- Load `frontend/dist`, `ffmpeg`, etc. via `sys._MEIPASS` when `getattr(sys,
  "frozen", False)`.
- macOS floor: whatever the numpy/scipy wheels require (currently ~macOS 12+).
  State it in the README.

### Expected bundle

- ~150–250 MB after dropping librosa (numpy+scipy ~100, ffmpeg ~80, rest small).
- `.dmg` compresses to ~90–150 MB.

### Reproducible build

- `scripts/build_app.sh` — `npm --prefix frontend ci && … run build`, regenerate
  the icon if missing, `pyinstaller "rekordbox bass notes.spec"`, ad-hoc
  codesign, then `.dmg` via `create-dmg` (falls back to `hdiutil create -format
  UDZO` with an `/Applications` symlink), and prints the artifact path + SHA256.
  `--no-dmg` stops after the `.app`.
- Run it on an Apple Silicon Mac matching the deployment floor. PyInstaller does
  **not** cross-compile — an Intel build needs an Intel (or Rosetta) machine.

---

## Code signing & notarization (Phase 2)

Only when v1 has proven useful. One-time setup, then scripted.

1. Apple Developer Program ($99/yr) → **Developer ID Application** certificate.
2. `codesign --deep --force --options runtime --timestamp --sign "Developer ID
   Application: <name> (<team>)" "rekordbox bass notes.app"`
   - hardened runtime; entitlements file allowing the JIT-free basics. A
     **non-sandboxed** Developer ID app can read `~/Library/Pioneer/…` without
     security-scoped bookmarks.
3. Zip → `xcrun notarytool submit --wait --apple-id … --team-id … --password
   <app-specific>` → `xcrun stapler staple "rekordbox bass notes.app"`.
4. Sign the `.dmg` too, staple it.

Result: friends double-click, no Gatekeeper dialog. Enables Sparkle-based
auto-update later.

---

## Testing

### Before every release

| Dimension | Cases |
|---|---|
| Arch | arm64 (Apple Silicon); Intel if shipping that build |
| macOS | oldest supported + latest |
| Rekordbox | one 6.x, one 7.x; ideally a friend's actual install |
| Library | small (<100) and large (10k+) tracks; streaming-only entries present |
| Files | local MP3, FLAC, AIFF, WAV; a relocated/offline file; M4A/AAC (once M1's ffmpeg lands — until then expect the "not supported" message) |
| State | Rekordbox running → refusal; Rekordbox closed → write + reopen shows the comment |
| Restore | write, restore prior backup, confirm revert + `quick_check` ok |
| First run | no `config.json` → detect → pick → analyse → save |

### Clean-machine test

Run the `.dmg` on a Mac (or fresh user account) that has never had Python /
Homebrew / this repo. That's the only real proof it's self-contained. Ideally do
this on one trusted friend's machine before sending to the rest.

---

## Release & updates

- **Versioning:** `MAJOR.MINOR.PATCH`; bump `MINOR` for features, `PATCH` for
  fixes, `MAJOR` if the token scheme or `dbfs_scale` changes (also bump
  `PRESET_LETTER`).
- **GitHub Releases (private repo):** attach the `.dmg`, write a short changelog,
  tag `vX.Y.Z`.
- **In-app update check:** on launch, GET the GitHub Releases API, compare to the
  running version, show a dismissible "vX.Y.Z is available → download" banner.
  No auto-install pre-signing.
- **Changelog entry must call out** any Rekordbox-version compatibility change.

---

## Risks & support plan

| Risk | Mitigation / message to friends |
|---|---|
| Rekordbox schema/key changes in an update | Pin `pyrekordbox`; test against a friend's install first; "don't update Rekordbox until I confirm." Ship a new build when `pyrekordbox` catches up. |
| `pyrekordbox` writes are "experimental" | Backup before every write + one-click restore + post-write `quick_check`. Say so plainly in the first-run screen. |
| User writes while Rekordbox is open | Two independent guards already; plus the banner. |
| Rekordbox cloud/library sync races the DB | First-run note: "pause Rekordbox sync while using this." |
| Backup folder fills the disk | `BACKUP_KEEP` default 20; show total size in the Backups panel. |
| Unsigned-app confusion | README with the exact right-click→Open / `xattr` steps and a screenshot. |
| A friend on Intel | Ask first; ship an `x86_64` build or tell them to wait. |
| Something breaks in the field | Logs at `~/Library/Logs/rekordbox bass notes/`; an in-app "Copy diagnostics" button; you fix and re-release. |

Set expectations explicitly: this is a personal tool shared among friends, not a
supported product; it can break when Rekordbox updates.

---

## Milestones & effort (remaining)

Phase 0 already covered the librosa drop, runtime config, human errors, the
backup endpoints, and the static mount.

| # | Milestone | Status | Left to do |
|---|---|---|---|
| M0 | One process | ✅ | `launcher.py` — pywebview + `webbrowser` fallback, free `127.0.0.1` port, uvicorn thread, single-instance `flock`, graceful shutdown |
| M1 | Deps | ✅ | ffmpeg fallback decode via `imageio-ffmpeg`; `requirements.txt` pinned |
| M2 | Loose ends | 🟡 | ✅ file logging + `/api/diagnostics` + Copy-diagnostics button; ✅ native-dialog bridge (`/api/pick-file`, `BrowseButton`) — untested in a real window; ⬜ RB v5 path variant |
| M3 | ~~UI panels~~ | ✅ | restore panel, Rekordbox banner + 5 s health polling, no-library screen, version footer, 70/30 layout, analysis cache, batch accordion, audio player + EQ |
| M4 | Package | 🟡 | ✅ `.icns` (placeholder), ✅ `rekordbox bass notes.spec` — **arm64 build succeeds, headless smoke test passes**, ✅ `scripts/build_app.sh`; ⬜ run through a GUI window; ⬜ `create-dmg` polish; ⬜ clean-machine `.dmg` check |
| M5 | Field test | ⬜ | clean-machine / friend's-Mac run; fix what breaks; release to 1–2 people |
| M6 | Ship | 🟡 | ✅ update-check endpoint + `UpdateBanner` + `last_seen_version`; ⬜ set `UPDATE_REPO`, cut the first tagged release |
| M7 *(optional)* | Signing | ⬜ | Developer ID sign + notarize + staple (`.app` and `.dmg`) |

Remaining to a shareable v1: a GUI-window pass on the build, `.dmg` packaging
polish, the RB v5 path check, and a clean-machine field test (M5).

---

## Execution notes (model & reasoning)

| Phase | Model | Reasoning |
|---|---|---|
| M0, M1, M2, M3, M6 | Sonnet 5 | `think` |
| M4 (PyInstaller — trial and error, read tracebacks) | Sonnet 5 | `think`, iterate against real `pyinstaller` runs |
| M5 (field debugging) | Sonnet 5 | `think` |
| M7 (signing) | Sonnet 5 | `think`; follow Apple's current docs, don't rely on memorized commands |

_(M1's DSP-correctness `think hard` item — the librosa→scipy resampler swap — is
done, in Phase 0.1.)_
