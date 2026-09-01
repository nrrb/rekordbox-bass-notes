# Distribution Plan — Rekordbox Comment Tagger for macOS

Turning the POC into a tool a handful of DJ friends can install and use on their
own Macs, against their own Rekordbox libraries.

See [`PLAN.md`](PLAN.md) for the app itself and [`README.md`](README.md) for dev
setup. This document is only about packaging and shipping.

---

## Phase 0 — parallel-safe prep — ✅ complete

Backend-only / additive hardening done **without disturbing the `npm run dev` +
`uvicorn --reload` loop**, so UI tweaking could continue alongside. Decisions
locked: app name **RekordboxTagger**; **soundfile-only** decoding for now
(M4A/AAC/ALAC → a clear "not supported yet" error, `ffmpeg` in M4); **both**
backup endpoints added.

| # | Item | Touches | Status |
|---|------|---------|--------|
| 0.1 | **Drop librosa** → `soundfile` decode + `scipy.signal.resample_poly` to `AUDIO_SR`. Removed `audio_res_type`. Re-ran `calibrate.py`: 1 of ~117 tracks shifts one digit at a boundary → **`dbfs_scale` unchanged, `PRESET_LETTER=B`**. `AudioDecodeError` for unsupported/corrupt; M4A/AAC/ALAC → "not supported yet". audioread `DeprecationWarning` noise gone. | `analysis.py`, `config.py`, `requirements.txt` | ✅ |
| 0.2 | **Runtime config** — `backend/runtime.py`: `RuntimeConfig {db_path, backup_dir}` persisted to JSON (`~/Library/Application Support/RekordboxTagger/config.json` frozen, `./.rkbx-config.json` gitignored in dev). Precedence env → file → default; **default db_path = "" (auto-locate the real library)**. `/api/db/switch` writes it (sticky across restart — verified). `db.backup()` / `_prune_backups` / `restore.py` read `backup_dir` from it. | `runtime.py` (new), `db.py`, `restore.py`, `main.py` | ✅ |
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
  (NDJSON, one line per track). M4A/AAC/ALAC → clear "not supported yet".
- **Backups API** — `GET /api/backups` (listing + live-DB stats),
  `POST /api/backups/{name}/restore` (guarded, snapshots current DB first). CLI
  `python -m backend.restore` shares the same code.
- **Human errors** — `humanize()` maps the common failures to plain `detail`
  sentences.
- **One-process ready** — FastAPI serves `frontend/dist` at `/` when a build is
  present (skipped in dev).
- **Runtime config** — `backend/runtime.py`: `db_path` + `backup_dir` persisted;
  precedence env → `config.json` → default.

UI is being iterated separately; the panels below (first-run screen, restore
panel, Rekordbox banner) are pending and best folded into that work.

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

### 1. One process — 🟡

- ✅ FastAPI serves `frontend/dist` at `/` (`sys._MEIPASS`-aware), `/api/*` first,
  skipped when no build is present.
- ⬜ **CORS in frozen mode**: `allow_origins` is hardcoded to
  `http://localhost:5173`. In the packaged app the SPA is same-origin on
  `127.0.0.1:<port>`, so relax/disable CORS when `sys.frozen`.
- ⬜ Build the SPA into the bundle (part of M4).

### 2. Launcher — ⬜

- `launcher.py` (PyInstaller entry point):
  1. resolve/first-run config (below), set up logging to
     `~/Library/Logs/RekordboxTagger/`.
  2. bind `127.0.0.1:0`, read back the port; single-instance lockfile in the
     app-support dir.
  3. start uvicorn in a thread.
  4. open a **pywebview** window at `http://127.0.0.1:<port>` (one dependency; a
     real window instead of a stray browser tab). Fallback: `webbrowser.open`.
  5. window close → uvicorn shutdown → exit.

### 3. Dependency slimming — 🟡

- ✅ **librosa dropped** (→ numba → llvmlite, ~300–400 MB): decode is
  `soundfile`/libsndfile (WAV/AIFF/FLAC/MP3/OGG), resample is
  `scipy.signal.resample_poly`. Recalibration: 1/117 tracks shifted one digit at
  a boundary → `dbfs_scale` / `PRESET_LETTER` unchanged.
- ⬜ **`ffmpeg` for M4A/AAC/ALAC** — add `imageio-ffmpeg` (`get_ffmpeg_exe()`),
  route those extensions through it; drop the "not supported yet" error. (M4.)
- ⬜ **Pin the rest of `requirements.txt`** (numpy/scipy/soundfile/fastapi/
  uvicorn/psutil are still ranges) for reproducible builds.

Runtime deps after M4: `numpy`, `scipy`, `soundfile`, `pyrekordbox` (**pinned
`==0.4.4`**), `sqlcipher3-wheels`, `fastapi`, `uvicorn`, `psutil`, `pywebview`,
`imageio-ffmpeg`.

### 4. Config & writable paths — 🟡

- ✅ `backend/runtime.py` — `db_path` + `backup_dir` persisted to
  `config.json` (`~/Library/Application Support/RekordboxTagger/` frozen,
  `./.rkbx-config.json` in dev). Precedence env → file → default. `/api/db/switch`
  and the restore endpoint write it.
- ✅ Backups default to **`~/Music/RekordboxTagger Backups/`** when frozen
  (`backend/backups/` in dev).
- ⬜ **Logging** — set up file logging to `~/Library/Logs/RekordboxTagger/` (for
  "Copy diagnostics"). Nothing writes there yet.
- ⬜ Persist an **app version** / `last_seen_version` for the update check.

### 5. First-run library setup — 🟡

- ✅ Auto-locates the library (`detect_library_path()`); `humanize()` turns
  "not found" into a plain message; `/api/health` reports `db_kind` and
  `detected_library_path`.
- ⬜ **Frontend "can't find library" state** — when health has no `db_path`,
  show a locate-your-`master.db` screen instead of a broken table.
- ⬜ **Native file dialog** — `DbSwitcher` has a path *text field*; in the
  packaged app wire it to `window.create_file_dialog()` (pywebview).
- ⬜ Confirm the v5 / v6 / v7 directory variants all resolve (pyrekordbox
  handles 6/7; check 5).

### 6. Restore in the UI — 🟡

- ✅ `GET /api/backups` (listing + live-DB stats via `RekordboxDB.stats()`) and
  ✅ `POST /api/backups/{name}/restore` (guarded, snapshots first, reopens).
- ⬜ **Restore panel** — a "Backups" screen; each row shows what's inside (USN,
  track count, tokens written, recent edits) so a non-technical user can pick.

### 7. Error surfacing — ✅

`humanize()` in `main.py` maps library-not-found, Rekordbox-open, audio-moved,
decode/format failure, and unsupported-DB-version to plain sentences in the API
`detail`; applied to analyze, batch-stream (per track), both write paths, and the
DB switch. Frontend renders `detail` as-is. (Raw detail → logs once §4 logging
lands.)

### 8. Rekordbox-running UX — ⬜

`/api/health` already reports `rekordbox_running`; the header shows a status word
and Save is disabled. ⬜ Turn it into a **persistent top banner with a Re-check
button** so it's unmissable.

### 9. App polish — ⬜

- **Icon** — a `.icns` (a `.png` run through `iconutil` / an online converter);
  referenced from the PyInstaller spec / `Info.plist`.
- **About / version** — a single `__version__` (e.g. `backend/__init__.py`),
  surfaced in `/api/health` and shown in the UI footer; drives the update check.
- **Window title** — `Info.plist` `CFBundleName` + the SPA `<title>`.

---

## Build pipeline

### PyInstaller spec essentials

```
pyinstaller --name RekordboxTagger --windowed --noconfirm \
  --osx-bundle-identifier com.<you>.rekordboxtagger \
  --target-arch arm64 \
  --collect-all pyrekordbox \
  --collect-all soundfile \
  --collect-all imageio_ffmpeg \
  --collect-binaries sqlcipher3 \
  --collect-all scipy --collect-all numpy \
  --add-data "frontend/dist:frontend/dist" \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.protocols.websockets.websockets_impl \
  --hidden-import uvicorn.lifespan.on \
  launcher.py
```

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

- A `scripts/build_app.sh` that: `npm ci && npm run build`, `pyinstaller
  RekordboxTagger.spec`, `create-dmg`, prints the artifact path + SHA256.
- Run it on an Apple Silicon Mac matching the deployment floor. PyInstaller does
  **not** cross-compile — an Intel build needs an Intel (or Rosetta) machine.

---

## Code signing & notarization (Phase 2)

Only when v1 has proven useful. One-time setup, then scripted.

1. Apple Developer Program ($99/yr) → **Developer ID Application** certificate.
2. `codesign --deep --force --options runtime --timestamp --sign "Developer ID
   Application: <name> (<team>)" RekordboxTagger.app`
   - hardened runtime; entitlements file allowing the JIT-free basics. A
     **non-sandboxed** Developer ID app can read `~/Library/Pioneer/…` without
     security-scoped bookmarks.
3. Zip → `xcrun notarytool submit --wait --apple-id … --team-id … --password
   <app-specific>` → `xcrun stapler staple RekordboxTagger.app`.
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
| Something breaks in the field | Logs at `~/Library/Logs/RekordboxTagger/`; an in-app "Copy diagnostics" button; you fix and re-release. |

Set expectations explicitly: this is a personal tool shared among friends, not a
supported product; it can break when Rekordbox updates.

---

## Milestones & effort (remaining)

Phase 0 already covered the librosa drop, runtime config, human errors, the
backup endpoints, and the static mount.

| # | Milestone | Left to do | Rough effort |
|---|---|---|---|
| M0 | One process | `launcher.py` + pywebview, `127.0.0.1:0` port, graceful shutdown, single-instance lock, relax CORS when `sys.frozen` | ~0.5 day |
| M1 | Deps | bundle `ffmpeg` (`imageio-ffmpeg`) for M4A/AAC/ALAC; pin the rest of `requirements.txt` | ~0.5 day |
| M2 | Config / first run | file logging to `~/Library/Logs/RekordboxTagger/`; `__version__`; frontend "can't find library" screen; native file dialog for "use a different database…" | ~0.5–1 day (UI) |
| M3 | UI panels | restore panel; persistent Rekordbox-running banner; icon + About/version footer | ~1 day (UI) |
| M4 | Package | PyInstaller spec that runs frozen (sqlcipher3 / ffmpeg / data-file iterations); `scripts/build_app.sh` → `.dmg` (arm64) | ~1–2 days |
| M5 | Field test | clean-machine / friend's-Mac run; fix what breaks; release to 1–2 people | ~0.5–1 day + iteration |
| M6 | Ship | wider release; in-app update-check banner | ~0.5 day |
| M7 *(optional)* | Signing | Developer ID sign + notarize + staple (`.app` and `.dmg`) | ~0.5 day one-time |

Total remaining to a shareable v1: roughly **3.5–5 focused days**, most of it in
M4. M2/M3 are largely UI and can ride along with the UI tweaking already underway.

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
