# Distribution Plan — Rekordbox Comment Tagger for macOS

Turning the POC into a tool a handful of DJ friends can install and use on their
own Macs, against their own Rekordbox libraries.

See [`PLAN.md`](PLAN.md) for the app itself and [`README.md`](README.md) for dev
setup. This document is only about packaging and shipping.

---

## Phase 0 — parallel-safe prep (in progress)

Backend-only or purely additive work that hardens the app for other people's
machines **without disturbing the `npm run dev` + `uvicorn --reload` loop**, so
UI tweaking can continue alongside it. Decisions locked: app name
**RekordboxTagger**; **soundfile-only** decoding for now (M4A/AAC/ALAC → a clear
"format not supported yet" error, `ffmpeg` bundled in M4); **both** backup
endpoints added now.

| # | Item | Touches | Status |
|---|------|---------|--------|
| 0.1 | **Drop librosa** → `soundfile` decode + `scipy.signal.resample_poly` to `AUDIO_SR`. Remove `audio_res_type`. Re-run `calibrate.py`; re-freeze `dbfs_scale` only if the shift is material (keep `PRESET_LETTER=B` — no tokens on a real library yet). Also kills the audioread `DeprecationWarning` noise. | `analysis.py`, `config.py`, `requirements.txt` | — |
| 0.2 | **Runtime config** — `backend/runtime.py`: a mutable `RuntimeConfig {db_path, backup_dir}` persisted to JSON. Location: `~/Library/Application Support/RekordboxTagger/config.json` when frozen, repo-local `./.rkbx-config.json` (gitignored) in dev. Precedence: env → config.json → default/autodetect. `/api/db/switch` writes it (so the choice is sticky across restart). `backup()` / `restore.py` read `backup_dir` from it. **Dev defaults unchanged.** | `runtime.py` (new), `db.py`, `restore.py`, `main.py` | — |
| 0.3 | **Human error messages** — map known failures (library not found, Rekordbox open, audio file moved, decode/format failure, key/decrypt failure) to plain sentences in the API `detail`. Frontend already just renders `detail`, so no UI change. | `main.py` (+ small helper) | — |
| 0.4 | **Backup endpoints** — `GET /api/backups` (JSON of `restore.list_backups()` + live-DB stats) and `POST /api/backups/{name}/restore` (guarded: Rekordbox closed → snapshot current DB → restore → reopen, behind `_swap_lock`). Additive routes; the restore **panel** is separate UI work. | `main.py`, `restore.py` (refactor list to return data) | — |
| 0.5 | **Additive static mount** — `app.mount("/", StaticFiles(frontend/dist, html=True))` after the `/api` routes, only if the dir exists. Lets `uvicorn` alone serve a built SPA for one-process testing; **`npm run dev` stays the dev path.** | `main.py` | — |
| 0.6 | Doc sync — PLAN.md (librosa refs, new endpoints, config), README (ffmpeg now optional, endpoints, config.json). | `PLAN.md`, `README.md` | — |

Deferred to the main milestones (they *are* UI, or need a stable UI / dep tree):
`launcher.py` + pywebview (M0 tail), first-run library picker & "Change library…"
control (M2, fold into UI work), restore **panel** (M3, fold into UI work),
PyInstaller spec (M4), `ffmpeg` bundling (M4).

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

## Architecture changes (POC → app)

### 1. One process

- `npm run build` → `frontend/dist/`.
- FastAPI mounts it: `app.mount("/", StaticFiles(directory=DIST, html=True))`,
  `/api/*` routes declared first. Resolve `DIST` via `sys._MEIPASS` when frozen.
- Drop the Vite dev server from the shipped product (still used in dev).

### 2. Launcher

- `launcher.py` (PyInstaller entry point):
  1. resolve/first-run config (below), set up logging to
     `~/Library/Logs/RekordboxTagger/`.
  2. bind `127.0.0.1:0`, read back the port; single-instance lockfile in the
     app-support dir.
  3. start uvicorn in a thread.
  4. open a **pywebview** window at `http://127.0.0.1:<port>` (one dependency; a
     real window instead of a stray browser tab). Fallback: `webbrowser.open`.
  5. window close → uvicorn shutdown → exit.

### 3. Dependency slimming (do this first — biggest packaging win)

Replace **librosa** (→ numba → llvmlite, ~300–400 MB and the flakiest PyInstaller
target) with:

- decode: `soundfile` (libsndfile; WAV/AIFF/FLAC, MP3 on ≥1.1) + a bundled
  **`ffmpeg`** (`imageio-ffmpeg`, `get_ffmpeg_exe()`) for AAC / M4A / ALAC.
- resample to `AUDIO_SR`: `scipy.signal.resample_poly`.

Then re-run `backend/calibrate.py` and confirm the per-band dBFS numbers don't
shift meaningfully; if they do, re-freeze `dbfs_scale` and bump `PRESET_LETTER`.

Remaining runtime deps: `numpy`, `scipy`, `soundfile`, `pyrekordbox` (**pinned
`==0.4.4`**), `sqlcipher3-wheels`, `fastapi`, `uvicorn`, `psutil`, `pywebview`,
`imageio-ffmpeg`.

### 4. Config & writable paths

A read-only `.app` can't write beside itself. Introduce a persisted config and
move writable state out.

- `~/Library/Application Support/RekordboxTagger/config.json` — chosen library
  path, backup folder, last-seen version.
- Backups default to **`~/Music/RekordboxTagger Backups/`** — somewhere a DJ will
  actually look, not `~/Library/Application Support`.
- Logs → `~/Library/Logs/RekordboxTagger/`.
- Config precedence: env var (for the developer) → `config.json` → autodetect.
- `settings` becomes mutable-at-runtime for `db_path` / `backup_dir` (already
  half-done via `/api/db/switch`).

### 5. First-run library setup

- On launch with no `config.json`: call `detect_library_path()`, show
  *"Found your Rekordbox library at `<path>` — use it?"* with **Change…** (native
  file picker) and a "not found" path.
- Handle Rekordbox 5 / 6 / 7 directory variants and "file missing."
- The existing `DbSwitcher` "sample vs live" control becomes **"Change library…"**
  (there is no sample in a shipped build).

### 6. Restore in the UI

Friends won't run `python -m backend.restore`. Promote it to a screen:

- `GET /api/backups` — the `backend/restore.py` listing as JSON (filename, time,
  sizes, USN, track count, tokens-written count, recent edits) + the live DB's
  stats.
- `POST /api/backups/{name}/restore` — guarded (Rekordbox closed), snapshots the
  current DB to `*_prerestore.db` first, then restores. Reuses `restore.py`.
- UI: a "Backups / Restore" panel; each row shows what's inside so a non-technical
  user can pick the right one.

### 7. Error surfacing

Every 500 currently returns `TypeName: message`. Map the common cases to plain
sentences shown in the UI:

| Cause | Message |
|---|---|
| library not found | "Couldn't find your Rekordbox library. Click *Change library…*" |
| Rekordbox running | "Rekordbox is still open — quit it and click *Re-check*." |
| audio file moved | "This track's audio file has moved or is offline." |
| decode failure | "Couldn't read this track's audio (unsupported or corrupt file)." |
| key/decrypt failure | "This Rekordbox version isn't supported yet — please tell me your version." |

Keep the raw detail in the logs.

### 8. Rekordbox-running UX

A persistent banner at the top of the app whenever `rekordbox_running()` is true,
with a **Re-check** button. Not just a disabled Save button.

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
| Files | local MP3, M4A/AAC, FLAC, AIFF; a relocated/offline file |
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

## Milestones & effort

| # | Milestone | Rough effort |
|---|---|---|
| M0 | Single process: FastAPI serves `frontend/dist`; `launcher.py` + pywebview; ephemeral port; graceful shutdown | ~0.5 day |
| M1 | Drop librosa → `soundfile` + `imageio-ffmpeg` + `scipy` resample; re-verify calibration | ~0.5–1 day |
| M2 | Config persistence, writable backup/log paths, first-run library picker, "Change library…" | ~1 day |
| M3 | Restore UI (`/api/backups`, panel); human error messages; Rekordbox-running banner | ~1 day |
| M4 | PyInstaller spec that actually runs frozen (sqlcipher3 / ffmpeg / data-file iterations); `build_app.sh` + `.dmg` | ~1–2 days |
| M5 | Clean-machine test on a friend's Mac; fix what breaks; first release to 1–2 people | ~0.5–1 day + iteration |
| M6 | Wider release; in-app update-check banner | ~0.5 day |
| M7 *(optional)* | Developer ID signing + notarization pipeline | ~0.5 day one-time |

Total to a shareable v1: roughly **5–7 focused days**, most of it in M4.

---

## Execution notes (model & reasoning)

| Phase | Model | Reasoning |
|---|---|---|
| M0, M2, M3, M6 | Sonnet 5 | `think` |
| M1 (resampler swap — DSP correctness) | Opus 5 or Sonnet 5 | **`think hard`** |
| M4 (PyInstaller — lots of trial and error, read tracebacks) | Sonnet 5 | `think`, iterate against real `pyinstaller` runs |
| M5 (field debugging) | Sonnet 5 | `think` |
| M7 (signing) | Sonnet 5 | `think`; follow Apple's current docs, don't rely on memorized commands |
