# BL22 Mail-in XAS Portal

User portal for the SSRL BL22 high-throughput XAS mail-in program: sample frames and barcodes,
sample and measurement definitions, shipping/storage tracking, and data viewing/export.
The beamline control software reads measurement definitions from, and uploads data to, the backend.

Requirements: [docs/requirements.md](docs/requirements.md)

| Directory | Content |
|---|---|
| `backend/` | FastAPI app (Python 3.12, MongoDB) |
| `frontend/` | Vite + React + TypeScript, Mantine UI, TanStack Query |
| `tools/` | Development helpers, e.g. a fake control software (not yet created) |
| `deploy/` | nginx and systemd configuration (not yet created) |
| `docs/` | Requirements and design notes |

## Backend: local development

Prerequisite: [uv](https://docs.astral.sh/uv/) (`pip install uv`). uv installs the pinned Python 3.12 itself.

```bash
cd backend
uv sync                      # create .venv and install dependencies
cp .env.example .env         # then fill in the MongoDB connection
uv run uvicorn app.main:create_app --factory --reload --port 8010
```

- Health check: http://localhost:8010/mail-in-xas/api/health
- API docs (not in prod): http://localhost:8010/mail-in-xas/api/docs

Tests and linting:

```bash
uv run pytest                # DB tests are skipped unless HT_XAS_TEST_MONGODB_URI is set
uv run ruff check . && uv run ruff format --check .
```

## Frontend: local development

Prerequisite: Node.js 24+. Start the backend first (above).

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5180/mail-in-xas/
```

The dev server forwards `/mail-in-xas/api` to the backend on port 8010 (override with
`BACKEND_URL`), so frontend and API share one origin, as behind nginx in production.

| Command | Purpose |
|---|---|
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from the backend's API (needs `uv`; run after changing backend endpoints) |
| `npm test` | Unit tests (Vitest) |
| `npm run lint` | ESLint |
| `npm run build` / `npm run build:dev` | Production build for `/mail-in-xas/` or `/mail-in-xas/dev/` into `dist/` |

## Local ports

| Port | Service |
|---|---|
| 5180 | Frontend dev server (Vite) |
| 8010 | Backend (uvicorn) |

Never commit `.env` files, hostnames, connection strings or keys; this repository is public.
