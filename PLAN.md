# Rekordbox Bass-Profile Comment Tagger — POC Plan

## Goal

A local web app that reads the Rekordbox library database with `pyrekordbox`, lists
tracks in a React UI, and lets the user edit a single track's **Comment** field and
save it back to the database — with a confirmation step before every write.

The **ultimate goal** this POC builds toward: analyze the audio of a track and append
a bass-profile token to its comment, e.g. `B:L5M7H9`, where:

- `B:` is a fixed preset prefix.
- `L` / `M` / `H` are the Low / Medium / High sub-bands of the 20–150 Hz range.
- Each digit `0–9` encodes 0–99% strength in that band (digit `d` = `d0`–`d9`%).

This plan covers the full pipeline: comment read/write plumbing **and** the audio
analysis stage that produces the token.

---

## Architecture

```
┌─────────────────┐     HTTP/JSON      ┌──────────────────────┐    pyrekordbox      ┌─────────────────┐
│  React (Vite)   │ ◄───────────────►  │  FastAPI (Python)    │ ◄────────────────► │  master.db      │
│  - track list   │   GET  /tracks     │  - read via ORM      │   SQLCipher        │  (Rekordbox 6/7)│
│  - analyze      │   POST /analyze    │  - audio analysis    │                    │                 │
│  - edit comment │   PUT  /comment    │  - write + commit()  │                    └─────────────────┘
│  - confirm modal│                    │  - auto backup       │
└─────────────────┘                    └──────────────────────┘
```

Two dev processes: Vite dev server (frontend) proxying `/api` → Uvicorn (backend).

### End-to-end analysis flow

```
select track ──▶ "Analyze audio" ──▶ backend locates file (DjmdContent.FolderPath)
                                          │
                                          ▼
                              decode → mono, resample to 2 kHz
                                          │
                                          ▼
                        3× zero-phase Butterworth band-pass (log-spaced)
                          Low 20–39 Hz · Med 39–77 Hz · High 77–150 Hz
                                          │
                                          ▼
                per band: RMS → dBFS → digit 0–9 (per-band absolute dBFS scale)
                                          │
                                          ▼
                     token "B:l{dL}m{dM}h{dH}"  +  merged-comment preview
                                          │
                     user reviews band table + diff ──▶ confirm modal ──▶ PUT ──▶ commit()
```

---

## Tech stack

| Layer      | Choice                                   | Why |
|------------|------------------------------------------|-----|
| DB access  | `pyrekordbox` (`Rekordbox6Database`)      | Only library (any language) with sync-safe write support: handles the SQLCipher key, ORM over `DjmdContent`, and the `usn` / `rb_local_usn` bump Rekordbox needs on `commit()`. |
| Audio DSP  | `numpy`, `scipy`, `soundfile` | `soundfile`/libsndfile decodes (WAV/AIFF/FLAC/MP3/OGG); `scipy.signal` for `resample_poly` + Butterworth band-pass + RMS. (librosa dropped for packaging — see DISTRIBUTION.md 0.1.) |
| Backend    | FastAPI + Uvicorn                         | Minimal, typed, proxy-friendly. |
| Frontend   | React + Vite + TypeScript                 | Fast POC, simple dev proxy. |
| HTTP       | `fetch` + small hooks                     | No React Query needed for a POC. |

**System dependency:** none for the supported formats (libsndfile is bundled in the
`soundfile` wheel). `ffmpeg` will be added later for M4A/AAC/ALAC.

### Why `pyrekordbox` and not another language

`master.db` is SQLCipher-encrypted SQLite with a static, community-known key, so any
SQLCipher binding (Rust `rusqlite` + `bundled-sqlcipher`, Go `go-sqlcipher`, C/C++
SQLCipher, Node `better-sqlite3-multiple-ciphers`) can technically read and write it.
What those don't give you:

1. **Key acquisition** — `pyrekordbox download-key` fetches/caches it.
2. **Schema knowledge** — table/column names, relationships, enum columns.
3. **Sync bookkeeping** — per-row `usn`, library-wide `rb_local_usn`, `updated_at`,
   and `agentRegistry`/sequence rows. Skip it and Rekordbox may ignore, revert, or
   mis-sync the edit (especially with Rekordbox cloud/library sync enabled).

Other projects (`rekordcrate` in Rust, `crate-digger` in Java) target the USB
`export.pdb` format, not the desktop `master.db`, and are read-focused.

If a non-Python production version is wanted later: make the write in `pyrekordbox`,
diff `master.db` before/after `commit()` to capture the exact write footprint, then
port just that.

---

## Locked-in decisions

| Decision            | Value |
|---------------------|-------|
| Band edges          | **Log-spaced thirds of 20–150 Hz** → 20.0 / 39.1 / 76.6 / 150.0 Hz (displayed rounded: 20 / 39 / 77 / 150). Configurable. |
| Per-band metric     | Zero-phase Butterworth band-pass (order 8, SOS) → **RMS in dBFS** (0 dBFS = full-scale). |
| dBFS → digit        | **Per-band** linear map, **absolute** (referenced to digital full scale, not track loudness). `settings.dbfs_scale[band]` = `(min → digit 0, max → digit 9)`, clamped: `digit = clamp(floor((dbfs − min) / (max − min) * 10), 0, 9)`. Calibrated from p5/p95 of a sample of ~117 local tracks: **L −46→−18, M −23→−7, H −20→−9** (`backend/calibrate.py`). Frozen once tokens are written to the real DB — a recalibration must bump the preset letter (`B` → `C`). |
| Preset prefix       | `B:` — constant, configurable `PRESET_LETTER`. |
| Analysis window     | Whole track (RMS over full duration). |
| Token format        | `B:l6m9h7` — uppercase preset prefix, **lowercase** band letters so the digits stand out. |
| Comment merge       | **Prepend.** Strip every existing `B:l#m#h#` token (matched in either letter case), collapse leftover whitespace, then put the new token at the **front** of the remaining comment (joined by `comment_sep`). `action` = `replaced` if any existed, else `prepended`. |

---

## Prerequisites (one-time)

**Already set up in this repo**: `.venv/` (Python 3.11) with `pyrekordbox 0.4.4`,
`sqlcipher3-wheels 0.5.7`, `SQLAlchemy 2.0.52`. The app opens your real Rekordbox
library by default (auto-located). _(Early development used a `sample/master.db`
copy; that has since been removed — see the note under Build order.)_

1. **Python env:** use `.venv` (`.venv/bin/python`, `.venv/bin/pip`). Core deps:
   `pip install pyrekordbox sqlcipher3-wheels`. `pyrekordbox` needs an SQLCipher
   driver; `sqlcipher3-wheels` is a prebuilt one, so `import sqlcipher3` works with
   no compiler. **Only if that import fails**, build from source:
   `python -m pyrekordbox install-sqlcipher` (clones into `./.tmp/`; a trailing
   `Could not remove temporary directory '.tmp'` is harmless — `rm -rf .tmp` after).
2. **Database key:** no manual step. `pyrekordbox 0.4.4` resolves the Rekordbox 6/7
   key automatically. This version has **no** `download-key` subcommand —
   `python -m pyrekordbox --help` shows only `install-sqlcipher`. If opening a DB
   ever raises a key/decrypt error, upgrade `pyrekordbox` or pass `key=...`.
3. **Quit Rekordbox fully** whenever the backend writes — the DB is otherwise locked;
   the write fails or leaves inconsistent state. The backend enforces this (409).
4. **Rekordbox version:** `pyrekordbox` auto-locates `master.db` for v6
   (`~/Library/Pioneer/rekordbox/`) or v7 (`rekordbox7`). `/api/health` reports the
   resolved path. To use a different `master.db`, browse to it in the header (or set
   `REKORDBOX_DB_PATH`).
5. **Audio decoding** is `soundfile`/libsndfile (bundled) — no `ffmpeg` needed for
   WAV/AIFF/FLAC/MP3/OGG; M4A/AAC/ALAC not supported yet.

---

## Backend

### `backend/config.py`
Env-configurable: `REKORDBOX_DB_PATH` / `USE_LIVE_LIBRARY`, `RESULT_LIMIT`,
`AUDIO_SR` (500), `band_edges_hz` (20/39.15/76.63/150), `dbfs_scale` per band via
`DBFS_{MIN,MAX}_{L,M,H}` (see Locked-in decisions), `PRESET_LETTER` (`B`),
`FILTER_ORDER` (8), `COMMENT_SEP` (`" "`), `BACKUP_DIR`, `BACKUP_KEEP` (20).

### `backend/db.py` — `pyrekordbox` wrapper
- `RekordboxDB(db_path=None)` → `Rekordbox6Database`; `.db_path` resolved from the
  engine URL, for backups.
- `list_tracks()` → local-file tracks only (see Frontend §1).
- `get_track(id)` / `_get_raw_content(id)` → snapshot / live ORM row.
- `count_tracks()`, `count_local_tracks()`.
- `backup()` → `PRAGMA wal_checkpoint(FULL)`, copy `master.db` + `-wal`/`-shm` to
  `backend/backups/master_<ts µs>.db`, then prune to `settings.backup_keep` (default
  20; `BACKUP_KEEP=0` disables). Runs *before* the mutation, so a failed copy aborts
  the write.
- `set_comment(id, new_comment) -> (old, new, backup_path)`:
  1. **409** pre-flight if `rekordbox_running()` (psutil).
  2. `backup()`.
  3. capture `old = content.Commnt`; `content.Commnt = new_comment`.
  4. `db.commit()` — pyrekordbox re-checks Rekordbox (caught → rollback → 409) and
     bumps `rb_local_usn` + the global `agentRegistry` USN.
  5. `PRAGMA quick_check` → `DatabaseIntegrityError` (message names the backup) if
     not `ok`.
- Exceptions: `RekordboxRunningError` (409), `TrackNotFoundError` (404),
  `DatabaseIntegrityError` (500).

### `backend/restore.py` — CLI (no HTTP surface)
- `python -m backend.restore` — lists backup sets newest-first, each with: filename,
  time taken + "N ago", `.db`/`-wal`/`-shm` sizes, and **from inside the file**:
  `agentRegistry` USN, track count, count of tracks carrying a `B:l#m#h#` token, and
  the 3 most-recently-edited track titles + `updated_at`. Also prints the live DB's
  same stats for comparison.
- `python -m backend.restore <index|name-substring> [--yes]` — guards on
  `rekordbox_running()`, snapshots the current live DB to `*_prerestore.db` (restore
  is itself reversible), copies the chosen backup over the live file, deletes the
  live `-wal`/`-shm`. Requires the backend server stopped.

### `backend/analysis.py` — audio analysis
- `analyze_file(path) -> AnalysisResult`:
  - `load_audio`: `soundfile.read` → mono (mean of channels) →
    `scipy.signal.resample_poly` to `settings.audio_sr` (500 Hz; Nyquist 250 ≫ 150,
    keeps the order-8 Butterworth well-conditioned, max |pole| ~0.98). Matches the
    old librosa/soxr path within ~0.01 dB per band on real tracks. Unsupported /
    corrupt files raise `AudioDecodeError`. ~0.8 s/track.
  - For each band `[lo, hi]`:
    `sos = scipy.signal.butter(settings.filter_order, [lo/nyq, hi/nyq], 'band', output='sos')`
    (with a stability guard rejecting max |pole| ≥ 0.999)
    → `yb = scipy.signal.sosfiltfilt(sos, y)`
    → `dbfs = 20*log10(rms(yb) / (1/√2))`  (0 dBFS = full-scale sine, AES-17)
    → `digit = _digit(dbfs, band)` using the per-band `settings.dbfs_scale`.
  - `token = f"{settings.preset_letter}:L{dL}M{dM}H{dH}"`.
  - Returns `AnalysisResult` = per-band `{ band, hz_low, hz_high, rms, dbfs, digit }`
    + `token` + `{ path, sample_rate, duration_sec, n_samples }`.
- `analyze_samples(y, fs)` — same, on an already-decoded mono array (used by tests).
- `merge_token(comment, token) -> MergeResult`:
  - `re.sub(<preset>:L\dM\dH\d, token, comment, count=1)` if the pattern is present
    → `action="replaced"`; else append after `settings.comment_sep` → `"appended"`.
  - `existing_tokens` count reported so >1 stale duplicates can be flagged.
  - Single home for this logic — the frontend never does string surgery.
- CLI: `python -m backend.analysis TARGET… [--json] [--sr N] [--comment T]`,
  `TARGET` = audio file path or Rekordbox track ID.
- `backend/calibrate.py` — batch every local track → per-band dBFS percentile
  report + histogram + suggested `dbfs_scale` endpoints; writes `calibration.json`.

### `backend/main.py` — routes

| Method | Path                          | Body                          | Returns |
|--------|-------------------------------|-------------------------------|---------|
| GET    | `/api/health`                 | –                             | `{ version, db_path, db_kind (live|custom|none), detected_library_path, rekordbox_running, track_count, local_track_count }` — `none` + nulls when no DB is open; polled by the UI every 5 s |
| GET    | `/api/tracks?search=&limit=`  | –                             | `[{ id, title, artist, album, genre, comment, folder_path, has_file }]` — **local-file tracks only** |
| GET    | `/api/tracks/{id}`            | –                             | single track (any id, incl. streaming) |
| GET    | `/api/tracks/{id}/audio`     | (Range)                        | streams the local audio file (`FileResponse`, `Accept-Ranges: bytes` → seeking); 404 / 422 no local file |
| POST   | `/api/tracks/{id}/analyze`    | –                             | `{ id, title, artist, audio_path, sample_rate, duration_sec, bands:[…], token, current_comment, proposed_comment, merge_action, existing_tokens }` — **no write**; 404 / 422 (no local file) / 500 |
| POST   | `/api/tracks/analyze`         | `{ ids: [...] }`              | **NDJSON stream**, one line per track: `{id, index, total, ok, …}` (ok adds token/bands/proposed_comment/…; not-ok adds `error`). No write. |
| PUT    | `/api/tracks/{id}/comment`    | `{ token }` xor `{ comment }` | `{ id, old_comment, new_comment, backup_path }` — `token` → `merge_token` (prepend); guard (409) + WAL-checkpoint backup + `commit()` |
| PUT    | `/api/tracks/comments`        | `{ items: [{id, token\|comment}] }` | `{ backup_path, count, results:[{id, old_comment, new_comment}] }` — **atomic**: one backup, one `commit()`, one `quick_check`; any unknown id → 404, nothing written; dup ids → 422 |
| POST   | `/api/db/switch`              | `{ target: "live" }` or `{ target: "custom", path }` | Reopen the shared `RekordboxDB` (auto-locate, or a chosen `master.db`) **and persist to `config.json`**. Returns fresh `/api/health`. |
| GET    | `/api/backups`               | –                              | `{ backup_dir, live:{db_path,usn,track_count,tagged_count}, backups:[{name,taken,size,wal_size,shm_size,usn,track_count,tagged_count,recent,is_prerestore,error}] }` |
| POST   | `/api/backups/{name}/restore`| –                              | Guarded (409 if Rekordbox open) → snapshot current DB → `apply_restore` → reopen. Returns `{restored_from, prerestore_snapshot, …health}`. |

- Single shared DB instance; `lifespan` starts the server **even if it can't open
  one** (`_state["db"] = None` → health `db_kind:"none"`, DB endpoints → 503).
- **`backend/runtime.py`** — `RuntimeConfig {db_path, backup_dir}` loaded from
  `config.json` (env > file > default) at import; `/api/db/switch` and the restore
  endpoint write it. `settings` keeps the static/env knobs.
- Errors are humanised (`humanize()` / `_http()`): library-not-found, Rekordbox
  open, audio moved, decode/format failure, unsupported-DB-version → plain
  sentences in `detail`.
- CORS allowed for `http://localhost:5173`.
- Error mapping: **404** unknown id · **409** Rekordbox running · **422** audio file
  missing/unreadable · **500** decode or commit failure (message included).

---

## Frontend

### Views

Two-column workspace: the track list at **70%** width, a sticky **30%** detail
column on the right (stacks below on narrow screens).

1. **Track list** (`TrackTable.tsx`) — a **play/pause button** then Title / Artist /
   Album / Genre / Comment, with a client-side search box and a **checkbox per row**
   (row click also toggles) plus a select-all-shown header box. **Only tracks with a
   real local audio file are listed** (`list_tracks` filters on `has_file`).
1a. **Player** (`player.tsx` context + `PlayerPanel.tsx`) — top of the right column
   when something is playing: one shared `<audio>` streaming
   `GET /api/tracks/{id}/audio` (Range-enabled), a Web Audio `AnalyserNode`
   bar-chart EQ on a `<canvas>`, a seek bar with `m:ss` labels, play/pause, stop.
   **Analysis cache** (`analysisCache.tsx`): results are kept per track id for the
   life of the current library (cleared on DB switch / restore), so deselecting and
   reselecting a track shows its result immediately, and the single / batch flows
   share results both ways. `AnalysisDetail.tsx` renders the band table + token +
   `CommentDiff.tsx`, shared by both panels.
2. **Single panel** (`AnalyzePanel.tsx`) — right column when exactly 1 row selected.
   Shows the cached `AnalysisDetail` if present (button reads **Re-analyze**),
   otherwise **Analyze audio**. **Save to Rekordbox** → `ConfirmDialog.tsx` (old → new)
   → `PUT /…/comment` (disabled when the comment already carries the token).
3. **Batch panel** (`BatchPanel.tsx`) — right column when ≥2 rows selected. On
   selection it seeds the view from the cache; **Analyze N** streams only the
   not-yet-analysed ids (`done/total` progress). Per-track **accordion** rows —
   click to expand the full `AnalysisDetail`. **Save M** (M = tracks whose comment
   changes) → `BatchConfirmDialog.tsx` → `PUT /api/tracks/comments` (one atomic write).
4. Save buttons disable while Rekordbox is running; every write path shows the backend
   error (esp. "quit Rekordbox"). On success the panels call `refetch` so the table's
   Comment column updates.

### State
- `useTracks()` — list + `refetch`.
- `useAnalyze()` / `useUpdateComment()` — single analyse / write.
- `useBatchAnalyze()` — POSTs `ids`, iterates the NDJSON stream into a `Map<id, item>`
  with `{done,total}` progress and an `AbortController`.
- `useBatchUpdate()` — `PUT /api/tracks/comments`.
- Selection: `selectedIds: Set<string>` in `App`. No global store.

### Dev proxy
`vite.config.ts` proxies `/api` → `http://localhost:8000`.

---

## Project structure

```
writertest/
├── PLAN.md
├── README.md                 # setup + run steps
├── .gitignore
├── backend/
│   ├── requirements.txt       # fastapi, uvicorn, pyrekordbox, sqlcipher3-wheels,
│   │                          #   psutil, numpy, scipy, soundfile
│   ├── config.py              # env-configurable params
│   ├── db.py                  # pyrekordbox wrapper: reads, backup(), set_comment()
│   ├── analysis.py            # decode + band-pass + dBFS + token + merge (+ CLI)
│   ├── calibrate.py           # batch dBFS distribution report (CLI)
│   ├── restore.py             # list / restore master.db backups (CLI)
│   ├── inspect_db.py          # sanity-check a master.db copy (CLI)
│   ├── main.py                # FastAPI app + routes
│   └── backups/               # auto-written master.db backups (gitignored)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api.ts   types.ts
        ├── analysisCache.tsx (Context: results by track id)
        ├── player.tsx        (Context: one <audio> + Web Audio AnalyserNode)
        ├── hooks/
        │   ├── useHealth.ts (5 s poll)   useTracks.ts   useBackups.ts
        │   ├── useAnalyze.ts             useUpdateComment.ts
        │   └── useBatchAnalyze.ts        useBatchUpdate.ts
        └── components/
            ├── TrackTable.tsx        AnalysisDetail.tsx (shared)
            ├── PlayerPanel.tsx       AnalyzePanel.tsx     ConfirmDialog.tsx
            ├── BatchPanel.tsx        BatchConfirmDialog.tsx
            ├── CommentDiff.tsx       DbSwitcher.tsx
            └── NoLibrary.tsx  RekordboxBanner.tsx  RestorePanel.tsx
```

_(No `CommentEditor.tsx` — free-text comment editing was in the original sketch but
the core loop is analyse → confirm → save; add it later if wanted.)_

---

## Build order

> _Steps 1–5 were developed and tested against a `sample/master.db` — a copy of the
> library. That copy was removed once the write path was proven; the app now
> defaults to the real library (auto-located), with a "use a different database…"
> control for a copy elsewhere. Historical references below are left as-is._

1. **Backend read-only** — scaffold FastAPI, `open_db()`, `GET /api/tracks` +
   `/api/health`. Verify against a **copy** of `master.db`; confirm titles / artists /
   comments come through.
2. **Frontend read-only** — Vite app, track table + search, wired to `/api/tracks`.
3. **Analysis module standalone** ✅ — `backend/analysis.py` + CLI. Verified on
   synthetic tones and 6 real tracks. `backend/calibrate.py` added.
   **Calibration done here** (ahead of step 6): per-band `dbfs_scale` set from the
   p5/p95 of a 117-track batch — L −46→−18, M −23→−7, H −20→−9 — giving a full
   0–9 digit spread on L and H (M stays top-heavy, matching the real distribution).
4. **`POST /analyze` + AnalyzePanel** ✅ — full analyze-and-preview loop, no writes.
5. **Write path** ✅ — `PUT /api/tracks/{id}/comment` (`token` merges via `merge_token`,
   `comment` replaces outright). `RekordboxDB.set_comment`: pre-flight
   `rekordbox_running()` guard (409) → WAL-checkpoint + `.db`/`-wal`/`-shm` backup to
   `backend/backups/` → capture old `Commnt` → mutate → `commit()` (which re-checks
   Rekordbox itself; caught as a second 409 path). Confirmed by reading pyrekordbox's
   source: plain attribute assignment is queued by `Base.__setattr__` and `commit()`
   bumps the row's `rb_local_usn` + the global `agentRegistry` USN before the SQL
   commit — no manual bookkeeping needed. Verified end-to-end: 422 (missing/both
   body fields), 404 (unknown id), 200 write with correct `old`/`new`/`backup_path`,
   persistence on a **freshly reopened** connection, `agentRegistry.localUpdateCount`
   +1 and `rb_local_usn`/`updated_at` bumped on the row, 409 via a monkeypatched guard
   (both at the `RekordboxDB` and FastAPI-route layers) with the comment left
   untouched. Tested against `sample/master.db`; a real pre-existing comment
   (a YouTube link) was incidentally overwritten mid-test and restored from the
   run's own backup.
6. **Go live** — `dbfs_scale` already calibrated (step 3); re-run `backend/calibrate.py`
   only if re-tuning. Point `REKORDBOX_DB_PATH` at the real `master.db`, quit Rekordbox,
   do one real edit, reopen Rekordbox, verify the comment shows on the track. Record the
   frozen `dbfs_scale` in the README.
7. **README** — quit Rekordbox · activate `.venv` · run `uvicorn` + `npm run dev`.

---

## Execution notes (model & reasoning)

Recommended settings for a Claude Code session executing this plan. Thinking keywords
(`think` → `think hard` → `think harder` → `ultrathink`) raise the per-turn reasoning
budget; `/model` switches model.

| Phase / step | Model | Reasoning | Why |
|--------------|-------|-----------|-----|
| Default for the project | Sonnet 5 | `think` (medium) | Well-trodden FastAPI + React patterns. |
| Step 1 — backend read-only scaffold | Sonnet 5 | low–`think` | Boilerplate. |
| Step 2 — frontend read-only | Sonnet 5 | low–`think` | Component skeletons, dev proxy. |
| **Step 3 — DSP module (`analysis.py`)** | Opus 5 or Sonnet 5 | **`think hard`** | Filter design, `sosfiltfilt`, RMS→dBFS reference, digit-clamp math — bugs are silent. Drop back to `think` once the standalone CLI produces sane values. |
| Step 4 — `POST /analyze` + AnalyzePanel | Sonnet 5 | `think` | HTTP wiring around a proven module. |
| **Step 5 — pyrekordbox write path** | Opus 5 or Sonnet 5 | **`think hard`** | Experimental `commit()`, `usn` / `rb_local_usn` bookkeeping, diff-inspecting the write footprint, verifying persistence across a DB reopen. |
| Step 6 — calibration | Sonnet 5 | `think` | Iterative judgment on real audio; human in the loop. |
| Step 7 — README | Sonnet 5 | low | Documentation. |

Pattern: start each phase at the higher setting to establish structure, then lower it
for fill-in. Opus fast mode is a good fit for steps 3 and 5 if available.

---

## Database safety (implemented)

- **Backup before every write** — `RekordboxDB.backup()` runs inside `set_comment()`
  *before* the row is touched: WAL-checkpoint, then copy `master.db` + `-wal` + `-shm`
  to `backend/backups/master_<ts>.db`. `shutil.copy2` raises on failure, so **no
  backup ⇒ no write**.
- **Retention** — after each backup, sets older than `settings.backup_keep` (default
  20; `BACKUP_KEEP=0` keeps all) are pruned, sidecars included.
- **Guards** — pre-flight `rekordbox_running()` → 409; pyrekordbox's own check in
  `commit()` → rollback → 409 (covers the launch-mid-request race); UI disables Save
  when Rekordbox is running; confirm dialog before any write.
- **Post-write `PRAGMA quick_check`** — not `ok` ⇒ `DatabaseIntegrityError` (500)
  whose message names the pre-write backup to restore. No auto-restore (a rare,
  ambiguous signal — the user decides).
- **Rollback** — any `commit()` exception discards the in-memory change.
- **Restore** — `python -m backend.restore` lists backups with contents (USN, track
  count, tokens written, recent edits) to pick from; restoring snapshots the current
  live DB first (`*_prerestore.db`), so it is itself reversible.
- **Scope** — one column (`Commnt`), one row per request. No deletes, no schema
  changes, no bulk ops.

Still not covered: same-disk backups only (no off-machine copy); no cross-process
lock (two writers, or two concurrent `PUT`s on the shared session, are unguarded —
single-user POC assumption); Rekordbox cloud/library sync can touch `master.db`
independently and isn't detected (pause it during use).

## Risks & caveats

- **`pyrekordbox` write support is officially "experimental."** `commit()` handles the
  `usn` / `rb_local_usn` bookkeeping (verified against source + empirically), but keep
  backups and verify in-app after each write.
- **Rekordbox locking / corruption** — never write while the app is open; the backend
  enforces this and backs up first. Pause Rekordbox cloud/library sync during testing.
- **dBFS → digit calibration** — done (step 3): per-band `dbfs_scale` from a 117-track
  batch. L and H use the full 0–9 range; **M stays weighted to 7–9** because 39–77 Hz
  really is near-maxed in modern club masters — that is the true distribution, not a
  scaling artifact. Endpoints must be frozen before writing to the live DB; recalibration
  ⇒ bump `preset_letter`.
- **Rekordbox track gain is not applied to the file** — analysis measures the raw file
  level, so two masters of the same track at different loudness score differently. If
  loudness-normalized digits are preferred, normalize to −14 LUFS before filtering
  (one-line change, add after calibration).
- **Format coverage** — libsndfile handles WAV/AIFF/FLAC/MP3/OGG; **M4A/AAC/ALAC
  raise `AudioDecodeError`** until `ffmpeg` is bundled (DISTRIBUTION.md M4). MP3
  sub-bass is usually intact.
- **Relocated / missing files** (external drives, cloud) — surfaced as `has_file: false`,
  analyze disabled.
- **Rekordbox 6 vs 7** — both use `Rekordbox6Database`; on a very new v7 build, confirm
  `pyrekordbox` recognizes the DB (health endpoint reports this).
- **Key availability** — `pyrekordbox 0.4.4` resolves the SQLCipher key automatically
  (confirmed). If a future/live DB errors on decrypt, upgrade `pyrekordbox` or pass
  `key=` explicitly.
- Scope is deliberately limited: the `Commnt` field, one track at a time, no auth,
  local-only. No bulk edit.
