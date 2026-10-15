# CreatorOS — Project Tracking

Hackathon window: 15 Oct – 20 Oct 2026 (23:00 IST). Results 22 Nov 2026.

## Status board

| # | Work item | Status | Notes |
|---|-----------|--------|-------|
| 1 | Requirements, system design, deployment design | ✅ done | `docs/01-03` |
| 2 | Mesh gateway module (chat / JSON / image / embeddings, mock for tests) | ✅ done | `app/mesh/client.py` |
| 3 | Data model (8 tables) + SQLAlchemy sessions (Postgres / SQLite) | ✅ done | `app/models.py`, `app/db.py` |
| 4 | Agents: strategist, writer (+revise), editor, visual, learner, brand | ✅ done | `app/agents/` |
| 5 | LangGraph pipeline with real editor loop | ✅ done | `app/graph/pipeline.py` |
| 6 | Brand voice learning + injection | ✅ done | `services/brand.py`, `agents/context.py` |
| 7 | Scheduling (APScheduler) + publishing (simulated, X API) | ✅ done | `services/scheduler.py`, `services/publisher.py` |
| 8 | Performance capture (user / simulated / platform) + learning cycle + injection | ✅ done | `services/learning.py` |
| 9 | Decision trail (per piece + global) | ✅ done | `models.Decision`, `/api/decisions` |
| 10 | Quality measure (CQS) + self-evaluation script | ✅ done | `services/quality.py`, `scripts/evaluate.py` |
| 11 | REST API | ✅ done | `app/api/routes.py`, `docs/08-api-reference.md` |
| 12 | Web UI (dashboard, brief, content detail w/ diff + trail, brands, learnings, decisions) | ✅ done | `app/static/index.html` |
| 13 | Unit tests | ✅ done (22) | `tests/unit` |
| 14 | Integration tests (pipeline + API) | ✅ done (16) | `tests/integration` |
| 15 | UI tests (Playwright) | ✅ done (9) | `tests/ui` |
| 16 | Docker image + compose (Postgres) + test compose | ✅ written | compose stack not yet run on a Docker host — **verify locally** |
| 17 | CI workflows (tests + organisers' checks) | ✅ done | `.github/workflows/` |
| 18 | README, design decisions, test plan, API reference | ✅ done | |
| 19 | **Run `scripts/evaluate.py` against real Mesh and commit `eval/results.md`** | ⏳ todo (needs your `rsk_` key) | the committed numbers are from mock mode until this runs |
| 20 | Push to public GitHub repo, add secrets `MESH_API_KEY` + `SUBMISSION_TOKEN`, confirm Actions pass | ⏳ todo | |
| 21 | Optional: X credentials for real publishing; demo video; deployed URL | ⏳ optional | |
| 23 | Platform-native previews (LinkedIn card with see-more fold, X card with char count, Instagram carousel slides, blog article) + Replay / Next / Reset / 1x-2x step-through of the agent run from the stored decision trail | ✅ done | v1.2 |
| 22 | Branded poster visuals (image-model background + typeset headline, fallback), pipeline strip, agent log with Mesh model/tokens, example briefs, best-slot recommendation | ✅ done | v1.1 |

## Remaining checklist before submission

1. `cp .env.example .env`, set `MESH_API_KEY`.
2. `docker compose up --build -d` → open http://localhost:8000 → *Seed demo brands* → run a brief.
3. `python scripts/evaluate.py --briefs 4 --platforms linkedin,x` → review `eval/results.md`; copy the
   headline numbers into README "Self-evaluation results".
4. `git init && git add . && git commit`, push to a **public** repo, add the two secrets, check the
   *Agent Arena Checks* workflow is green.
5. (Optional) record a 2-3 min demo: brief → trail → publish → performance → learn → regenerate.

## Risks

| Risk | Mitigation |
|---|---|
| Mesh model name for images differs from `openai/gpt-image-1` | configurable `MESH_IMAGE_MODEL`; pipeline keeps the prompt and continues if the image call fails |
| JSON-mode not supported by a chosen model | `chat_json` tolerates fenced / prose-wrapped JSON |
| Judges run without a key | `MESH_MOCK=1` makes the whole app and tests runnable offline, clearly labelled |
| Single-process scheduler | documented: one replica, or `SCHEDULER_ENABLED=0` on extra replicas |

## Change log

- 2026-10-15 — v1.0.0: full system, tests, docs, Docker, CI.
- 2026-10-15 — v1.1.0: poster visuals (always produced, image-model errors logged), status race fixed (`scoring` stage before `ready`), pipeline strip + agent log with per-call Mesh model/tokens, example briefs per demo brand, best-slot recommendation with reason, 46 tests.
- 2026-10-15 — v1.2.0: platform-native previews and run replay (step-by-step) on the piece page; 47 tests.
