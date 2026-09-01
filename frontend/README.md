# frontend

React + Vite + TypeScript SPA for rekordbox bass notes.

- **Dev:** `npm install` then `npm run dev` (port 5173, proxies `/api` → the
  FastAPI backend on :8000). Start the backend separately:
  `.venv/bin/uvicorn backend.main:app --reload --port 8000`.
- **Build:** `npm run build` → `dist/` (the backend serves this at `/` when it
  exists, for the packaged single-process app).
- **Lint:** `npm run lint` (oxlint).

Everything else — what the app does, the API, packaging — is in the repo-root
[`README.md`](../README.md), [`PLAN.md`](../PLAN.md), and
[`DISTRIBUTION.md`](../DISTRIBUTION.md).
