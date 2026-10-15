# CreatorOS — Requirements

Track 03 of Agent Arena 2026 (sponsor: Mesh API). Source: hackathon brief (`reference/CreatorOS.docx`).

## 1. Goal

A **closed-loop, self-improving content studio**: specialised agents plan, write, critique/revise, illustrate,
schedule and publish content, then **learn from performance feedback** so the next piece is better — while
staying in a **brand voice learned from the user's own content**. Every important decision is logged.

## 2. Functional requirements

| ID | Requirement | Brief section | Where implemented | Verified by |
|----|-------------|---------------|-------------------|-------------|
| FR-1 | Coordinator runs a pipeline of ≥3 **distinct** agents (own prompt / own job) and passes work between them | 1 | `app/graph/pipeline.py` (LangGraph `StateGraph`, named nodes), `app/agents/*` | `tests/integration/test_pipeline.py` |
| FR-2 | **Editor refinement loop**: editor critiques against concrete criteria; writer revises; output genuinely changes | 2 | `agents/editor.py`, `agents/writer.py::revise`, conditional edge `editor → reviser → editor` | `test_editor_loop_changes_the_draft`, `test_full_generation_pipeline` |
| FR-3 | **Brand voice** profile learned from >1 sample, injected into generation; different brands → visibly different output | 3 | `agents/brand.py`, `services/brand.py`, `agents/context.py::brand_block` | `test_brand_voice_learned_from_samples`, Experiment C in `scripts/evaluate.py` |
| FR-4 | Matching **image** generated via an image model reachable through Mesh | 4 | `agents/visual.py` — background from `openai/gpt-image-1` via Mesh, then `services/poster.py` typesets brand chip + headline + subline (Pillow); procedural background if the image model fails, failure recorded in the trail | `test_visual_is_always_produced_and_logged`, UI `test_pipeline_strip_agent_log_and_example_brief` |
| FR-5 | Finished piece **stored and queued** for a scheduled time; published when due | 4 | `services/studio.py::schedule_piece`, `services/scheduler.py` (APScheduler), `services/scheduling.py` best-slot recommendation with reason | `test_schedule_publish_feedback_learn_loop`, UI `test_schedule_flow` |
| FR-6 | **Performance feedback** (real / user-entered / simulated) captured and **fed back** so future content changes | 5 | `services/learning.py`, `agents/learner.py`, `learnings_block` in every agent prompt | `test_schedule_publish_feedback_learn_loop` (learnings injected into the next piece), Experiment B |
| FR-7 | **Auditable decision trail**: angle, edits, learnings — each record linked to its content piece with the reason | 6 | `models.Decision`, every agent writes through `Sink.decision` | `test_full_generation_pipeline`, UI `test_decision_trail_page_filters` |
| FR-8 | **Self-evaluation**: a defined quality measure + script that scores before/after editor and with/without learnings; numbers recorded in the repo | 7 | `services/quality.py` (CQS), `scripts/evaluate.py`, `eval/results.md` | `tests/unit/test_quality_and_learning.py` |
| FR-9 | Multi-platform adaptation: one brief → properly adapted pieces for several platforms | Tech stack | `platforms.py`, `ContentCreate.platforms` → campaign | `test_multi_platform_campaign_adapts_per_platform` |
| FR-10 | (Bonus) Real publishing through a platform API with engagement read back | Tech stack | `services/publisher.py` (X API v2), `scheduler.refresh_real_metrics` | manual (needs credentials) |
| FR-11 | Simple, good-looking web UI | Tech stack | `app/static/index.html` | `tests/ui/test_ui.py` (Playwright) |

## 3. Non-functional / submission requirements

| ID | Requirement | How it is met |
|----|-------------|---------------|
| NFR-1 | **Every LLM/AI call routes through Mesh API** (`https://api.meshapi.ai/v1`, `rsk_` key from `MESH_API_KEY`) | Single gateway module `app/mesh/client.py`; no other module imports an LLM SDK. Chat, image and embedding calls all go through it. |
| NFR-2 | Backend in Python with FastAPI | `app/main.py` |
| NFR-3 | `requirements.txt` lists a web framework and the LLM client | `fastapi`, `openai` (used against Mesh) |
| NFR-4 | No secrets in the repo; `.gitignore` ignores `.env` | `.env.example` only; `.gitignore` |
| NFR-5 | Automated checks workflow at `.github/workflows/agent-arena-2026-checks.yml`; secrets `MESH_API_KEY`, `SUBMISSION_TOKEN` | Workflow file copied verbatim from the organisers |
| NFR-6 | README explains what was built, how agents cooperate, key design decisions, self-evaluation results | `README.md`, `docs/06-design-decisions.md`, `docs/07-self-evaluation.md` |
| NFR-7 | PostgreSQL in deployment; easy install | `docker-compose.yml` (Postgres 16 + app); SQLite fallback for local dev/tests |
| NFR-8 | Tests: unit, integration, UI (Playwright) | `tests/unit`, `tests/integration`, `tests/ui`; CI in `.github/workflows/tests.yml` |
| NFR-9 | No faked features: agents are always called, the loop loops, learnings are real prompt inputs | Mock mode exists **only** for tests and is labelled in the UI footer; runtime refuses to start without a Mesh key unless `MESH_MOCK=1` is set explicitly |

## 4. Out of scope (deliberately)

- OAuth flows for LinkedIn / Instagram publishing (no public posting API without app review). X is supported when credentials are provided; everything else publishes in simulated mode and says so in the decision trail.
- Multi-user auth. The studio is single-tenant per deployment.
- Video content.

## 5. Judging criteria mapping

| Criterion | Evidence |
|---|---|
| Multi-agent orchestration | LangGraph graph with 6 named nodes, real conditional loop; `test_graph_structure_has_named_nodes_and_loop` |
| Core loop (editor) | Diff view in UI, versions table, `quality_before/after` on every piece |
| Core domain capability (feedback loop) | `learnings` + `learning_runs` tables, learnings injected and listed per piece (`learnings_applied`) |
| Supporting capability (brand voice, visuals, scheduling) | brand profile + stats, image per piece, APScheduler queue |
| Foundation / data model / ingestion | `app/models.py` (8 tables), sample ingestion, user-entered + simulated + platform metrics |
| Self-evaluation | `scripts/evaluate.py`, `eval/results.md` |
| Auditable decision trail | `/api/decisions`, Decision trail page, per-piece timeline |
| Code quality / reproducibility | Docker, tests, CI, `.env.example`, docs |
