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
                     token "B:L{dL}M{dM}H{dH}"  +  merged-comment preview
                                          │
                     user reviews band table + diff ──▶ confirm modal ──▶ PUT ──▶ commit()
```

---

## Tech stack

| Layer      | Choice                                   | Why |
|------------|------------------------------------------|-----|
| DB access  | `pyrekordbox` (`Rekordbox6Database`)      | Only library (any language) with sync-safe write support: handles the SQLCipher key, ORM over `DjmdContent`, and the `usn` / `rb_local_usn` bump Rekordbox needs on `commit()`. |
| Audio DSP  | `numpy`, `scipy`, `librosa`, `soundfile` | Band-pass filtering + RMS; `librosa.load` decodes/resamples most formats. |
| Backend    | FastAPI + Uvicorn                         | Minimal, typed, proxy-friendly. |
| Frontend   | React + Vite + TypeScript                 | Fast POC, simple dev proxy. |
| HTTP       | `fetch` + small hooks                     | No React Query needed for a POC. |

**System dependency:** `ffmpeg` (required by `librosa`/`audioread` for MP3/M4A/AAC).

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
| dBFS → digit        | **Per-band** linear map, **absolute** (referenced to digital full scale, not track loudness). `settings.dbfs_scale[band]` = `(min → digit 0, max → digit 9)`, clamped: `digit = clamp(floor((dbfs − min) / (max − min) * 10), 0, 9)`. Calibrated from p5/p95 of a 117-track sample: **L −46→−18, M −23→−7, H −20→−9** (`backend/calibrate.py`). Frozen once tokens are written to the real DB — a recalibration must bump the preset letter (`B` → `C`). |
| Preset prefix       | `B:` — constant, configurable `PRESET_LETTER`. |
| Analysis window     | Whole track (RMS over full duration). |
| Comment merge       | Regex `B:L\dM\dH\d` → replace first match in place; if absent, append after a space. Rest of the comment is preserved. |

---

## Prerequisites (one-time)

**Already set up in this repo** (verified 2026-09-01): `.venv/` (Python 3.11) with
`pyrekordbox 0.4.4`, `sqlcipher3-wheels 0.5.7`, `SQLAlchemy 2.0.52`; and
`sample/master.db`, a copy of the live database. Confirmed working:
`Rekordbox6Database("sample/master.db")` opens and reads 26 content rows + comments.

1. **Python env:** use `.venv` (`.venv/bin/python`, `.venv/bin/pip`). Core deps:
   `pip install pyrekordbox sqlcipher3-wheels`. `pyrekordbox` needs an SQLCipher
   driver; `sqlcipher3-wheels` is a prebuilt one, so `import sqlcipher3` works with
   no compiler. **Only if that import fails**, build from source:
   `python -m pyrekordbox install-sqlcipher` (clones into `./.tmp/`; a trailing
   `Could not remove temporary directory '.tmp'` is harmless — `rm -rf .tmp` after).
2. **Database key:** no manual step. `pyrekordbox 0.4.4` resolves the Rekordbox 6/7
   key automatically (confirmed against `sample/master.db`). This version has **no**
   `download-key` subcommand — `python -m pyrekordbox --help` shows only
   `install-sqlcipher`. If opening the *live* DB ever raises a key/decrypt error,
   upgrade `pyrekordbox` or pass `key=...` explicitly to `Rekordbox6Database`.
3. **Quit Rekordbox fully** whenever the backend writes — the DB is otherwise locked;
   the write fails or leaves inconsistent state. The backend enforces this (409).
4. **Rekordbox version:** `pyrekordbox` auto-locates `master.db` for v6
   (`~/Library/Pioneer/rekordbox/`) or v7 (`rekordbox7`). `/api/health` reports which
   DB was opened. The `No masterPlaylists6.xml found` warning when opening a bare
   copied `.db` is benign (playlist XML not copied alongside).
5. **Safety copy:** `sample/master.db` is the working copy — point `DB_PATH` at it for
   steps 1–5. Keep a second untouched copy. Switch `DB_PATH` to the live DB only after
   the write path is proven (step 6).
6. **Install `ffmpeg`** (`brew install ffmpeg`) for MP3/M4A/AAC decoding.

---

## Backend

### `backend/config.py`
Env-configurable: `REKORDBOX_DB_PATH`, `RESULT_LIMIT`, `AUDIO_SR` (500),
`AUDIO_RES_TYPE` (`soxr_hq`), `band_edges_hz` (20/39.15/76.63/150),
`dbfs_scale` per band via `DBFS_{MIN,MAX}_{L,M,H}` (see Locked-in decisions),
`PRESET_LETTER` (`B`), `FILTER_ORDER` (8), `COMMENT_SEP` (`" "`), `BACKUP_DIR`.

### `backend/db.py` — `pyrekordbox` wrapper
- `open_db()` → `Rekordbox6Database(path=settings.DB_PATH)` (defaults to auto-detect).
- `list_tracks()` → iterate `db.get_content()`, return
  `{ id, title, artist, album, comment, folder_path, has_file }`.
- `get_track(id)` → single row.
- `set_comment(id, new_comment)`:
  1. Refuse with **409** if a Rekordbox process is running (`psutil` / `pgrep`).
  2. Write a timestamped backup of `master.db` to `backend/backups/`.
  3. `content = db.get_content(ID=id)`; capture `old = content.Commnt`.
  4. `content.Commnt = new_comment`.
  5. `db.commit()`.
  6. Return `{ id, old_comment, new_comment }`.

### `backend/analysis.py` — audio analysis
- `analyze_file(path) -> AnalysisResult`:
  - `librosa.load(path, sr=settings.audio_sr, mono=True, res_type=settings.audio_res_type)`
    — 500 Hz; Nyquist 250 Hz ≫ 150 Hz, and low normalised band edges keep the
    order-8 Butterworth well-conditioned (max |pole| ~0.98). ~1 s/track warm.
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
| GET    | `/api/health`                 | –                             | `{ db_path, rekordbox_version, rekordbox_running }` |
| GET    | `/api/tracks?search=&limit=`  | –                             | `[{ id, title, artist, album, comment, has_file }]` |
| GET    | `/api/tracks/{id}`            | –                             | single track |
| POST   | `/api/tracks/{id}/analyze`    | –                             | `{ id, audio_path, sample_rate, bands:[{band,hz_low,hz_high,dbfs,digit}], token, current_comment, proposed_comment }` — **no write** |
| PUT    | `/api/tracks/{id}/comment`    | `{ token }` **or** `{ comment }` | `{ id, old_comment, new_comment }` — `token` branch calls `merge_token` server-side; both branches enforce Rekordbox-closed + backup + `commit()` |

- Single shared DB instance opened at startup, closed on shutdown (`lifespan`).
- CORS allowed for `http://localhost:5173`.
- Error mapping: **404** unknown id · **409** Rekordbox running · **422** audio file
  missing/unreadable · **500** decode or commit failure (message included).

---

## Frontend

### Views
1. **Track list** — table of Title / Artist / Album / Comment with a client-side
   search box and a "file present" indicator (analyze disabled when the file can't be
   found). Backend caps results (e.g. 500) for the POC.
2. **Analyze panel** (`AnalyzePanel.tsx`) — "Analyze audio" button → spinner → results:
   - Band table rows: `Low 20–39 Hz | −31.4 dBFS | 4`.
   - Proposed token `B:L4M7H9` in monospace.
   - Comment diff (`CommentDiff.tsx`): current comment with the old token struck
     through / new token highlighted (or the appended token highlighted).
3. **Comment editor** (`CommentEditor.tsx`) — `<textarea>` prefilled with the current
   comment for manual edits; Save disabled until changed.
4. **Confirmation modal** (`ConfirmDialog.tsx`) — on Save:
   > Update comment for **{title} — {artist}**?
   > Old: "{old}"
   > New: "{new}"
   > `[Cancel] [Confirm & Save]`
5. **Result toast** — success shows old→new; failure surfaces the backend message
   (especially "quit Rekordbox and retry").

### State
- `useTracks()` — fetch list, expose `refetch`.
- `useAnalyze(id)` — `POST /analyze`, returns bands + token + proposed comment.
- `useUpdateComment()` — `PUT`, on success patches the local list row and pops the toast.
- No global store; component state + hooks.

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
│   ├── pyproject.toml         # fastapi, uvicorn, pyrekordbox, sqlcipher3-wheels,
│   │                          #   psutil, numpy, scipy, librosa, soundfile
│   ├── config.py              # env-configurable params
│   ├── db.py                  # pyrekordbox wrapper
│   ├── analysis.py            # decode + band-pass + dBFS + token + merge (+ CLI)
│   ├── main.py                # FastAPI app + routes
│   └── backups/               # auto-written master.db backups (gitignored)
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── hooks/
        │   ├── useTracks.ts
        │   ├── useAnalyze.ts
        │   └── useUpdateComment.ts
        └── components/
            ├── TrackTable.tsx
            ├── AnalyzePanel.tsx
            ├── CommentDiff.tsx
            ├── CommentEditor.tsx
            └── ConfirmDialog.tsx
```

---

## Build order

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
7. **README** — quit Rekordbox · activate `.venv` · `brew install ffmpeg` ·
   run `uvicorn` + `npm run dev`.

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

## Risks & caveats

- **`pyrekordbox` write support is officially "experimental."** `commit()` handles the
  `usn` / `rb_local_usn` bookkeeping, but keep backups and verify in-app after each
  write.
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
- **`ffmpeg` dependency** for lossy formats; AAC/M4A low-end varies by encoder, MP3
  sub-bass is usually intact.
- **Relocated / missing files** (external drives, cloud) — surfaced as `has_file: false`,
  analyze disabled.
- **Rekordbox 6 vs 7** — both use `Rekordbox6Database`; on a very new v7 build, confirm
  `pyrekordbox` recognizes the DB (health endpoint reports this).
- **Key availability** — if `download-key` cannot fetch the cached key, it must be
  extracted from an installed Rekordbox; this is the one setup step that can block.
- Scope is deliberately limited: the `Commnt` field, one track at a time, no auth,
  local-only. No bulk edit.
