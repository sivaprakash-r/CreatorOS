# CreatorOS — Deployment Design

## 1. Topologies

| Mode | Command | DB | Use |
|---|---|---|---|
| Local dev | `uvicorn app.main:app --reload` | SQLite (`data/creatoros.db`) | development, demo |
| Docker Compose (recommended) | `docker compose up --build -d` | PostgreSQL 16 (container) | evaluation, demo video, deployed URL |
| Cloud (optional) | Cloud Run / any container host + managed Postgres | managed Postgres | shortlisted-submission URL |

## 2. Container

- Base image `python:3.11-slim`; non-root not required by the brief, image is ~250 MB.
- `app/` and `scripts/` are copied in; `data/` is a volume (`/app/data`) holding generated images and the
  SQLite file when Postgres is not used.
- `HEALTHCHECK` hits `/api/health`.
- Entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (single process; APScheduler runs in-process,
  so **run exactly one app replica** or disable the scheduler on all but one with `SCHEDULER_ENABLED=0`).

## 3. Compose stack

```
db  (postgres:16-alpine, volume pgdata, healthcheck pg_isready)
app (build ., env_file .env, DATABASE_URL → db, port 8000, volume appdata, depends_on db healthy)
```

Startup: the app creates the schema on boot (`Base.metadata.create_all`) — no migration tool is needed at
this size; `alembic` can be added when the schema starts changing in production.

## 4. Configuration (12-factor, all via env / `.env`)

| Variable | Default | Notes |
|---|---|---|
| `MESH_API_KEY` | — | **required** (`rsk_…`). App refuses to start without it unless `MESH_MOCK=1` |
| `MESH_BASE_URL` | `https://api.meshapi.ai/v1` | |
| `MESH_CHAT_MODEL` / `MESH_EDITOR_MODEL` | `openai/gpt-4o-mini` | any chat model on Mesh (`provider/model`) |
| `MESH_IMAGE_MODEL` | `openai/gpt-image-1` | any image model on Mesh |
| `MESH_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | used by the quality scorer |
| `DATABASE_URL` | SQLite | `postgresql+psycopg://user:pass@host:5432/db` in compose |
| `EDITOR_MAX_ROUNDS` / `EDITOR_PASS_SCORE` | `2` / `7.5` | loop bounds |
| `SCHEDULER_ENABLED` / `SCHEDULER_POLL_SECONDS` | `1` / `20` | |
| `SIMULATE_ENGAGEMENT` | `1` | synthesise engagement after a simulated publish |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | empty | enable real posting to X |

Secrets never enter the image: `.env` is git-ignored and passed at runtime via `env_file`.

## 5. Install & run (what a judge does)

```bash
git clone <repo> && cd creatorOS
cp .env.example .env            # put your rsk_ key in MESH_API_KEY
docker compose up --build -d    # http://localhost:8000
# optional: seed the two demo brands + first pieces
docker compose exec app python scripts/seed.py
```

Without Docker:

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## 6. Tests in containers

`docker compose -f docker-compose.test.yml run --rm tests` runs unit + integration + Playwright UI tests
inside Microsoft's Playwright Python image (browsers pre-installed), entirely offline (`MESH_MOCK=1`).

## 7. CI

- `.github/workflows/tests.yml` — unit/integration, then Playwright UI tests on every push.
- `.github/workflows/agent-arena-2026-checks.yml` — the organisers' checks (requires repo secrets
  `MESH_API_KEY` and `SUBMISSION_TOKEN`).

## 8. Operations

- Logs: structured one-line logs to stdout (`LOG_LEVEL`).
- Health: `GET /api/health` reports gateway URL, models, mock flag, scheduler state.
- Backups: `pgdata` volume (Postgres) + `appdata` volume (images).
- Scaling: the pipeline is CPU-light and I/O-bound on Mesh; FastAPI background tasks run generation.
  For heavier load move `generate_piece` to a worker (RQ/Celery) — the function is already session-safe and
  idempotent per `content_id`.
- Cost control: one piece ≈ 6-9 chat calls + 1 image + 2 judge calls + 2 embedding calls. Use
  `generate_image=false` in the brief form to skip images, and `MESH_CHAT_MODEL=openai/gpt-4o-mini`.

## 9. Security

- No secrets in code or images; `.gitignore` covers `.env*`.
- Only the Mesh gateway and (optionally) the X API are called out; no other egress.
- Input validation via Pydantic; SQLAlchemy parameterised queries; images served only from the app's own
  `data/images` directory by content id.
