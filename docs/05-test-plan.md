# CreatorOS — Test Plan

## Principles

- **Offline and deterministic.** All suites run with `MESH_MOCK=1`: the Mesh client returns canned,
  structurally faithful JSON per agent task, so orchestration, the editor loop, persistence, the learning
  cycle, the API and the UI are tested without network or cost. The mock editor requests a revision on odd
  rounds and accepts on even rounds, so the loop always runs at least once.
- **Mock is for tests only.** `tests/conftest.py` sets the env before the app is imported; the running
  product refuses to start without `MESH_API_KEY` unless `MESH_MOCK=1` is set explicitly.
- **Real-model behaviour is measured, not unit-tested**: `scripts/evaluate.py` against Mesh (see
  `docs/07-self-evaluation.md`).

## Levels

| Level | Location | Framework | Count | Runs |
|---|---|---|---|---|
| Unit | `tests/unit` | pytest | 22 | ~1 s |
| Integration | `tests/integration` | pytest + FastAPI `TestClient` + SQLite | 16 | ~5 s |
| UI (end-to-end) | `tests/ui` | **pytest-playwright** (Chromium) against a real uvicorn server | 9 | ~25 s |

### Unit (what is covered)

- `features.py`: hook-type classification, length buckets, feature extraction, style statistics.
- `quality.py`: platform-fit rules (limits, CTA, hashtag budget), cosine, voice similarity ordering, CQS shape.
- `learning.py`: engagement-score formula (rate & absolute), simulator determinism and ordering,
  feature → engagement table.
- `platforms.py`: aliases and rejection of unsupported platforms.
- `mesh/client.py`: JSON parsing with fences/prose, key enforcement, call recording, image/embedding mocks.
- Agents: editor verdict derived from threshold + hard limit; strategist/writer prompts actually contain the
  brand profile, the learnings and the engagement table (the "learning changes the prompt" guarantee).

### Integration

- `test_pipeline.py`: LangGraph graph has the named nodes and the `reviser → editor` loop edge; the loop
  changes the draft (v1 ≠ v2), decisions cover every agent with reasoning, the image file is written,
  `EDITOR_MAX_ROUNDS` caps the loop.
- `test_api.py`: health/platforms; brand creation + voice learning + validation; full generation
  (ready, rounds, CQS before/after, image endpoint, versions, linked decisions); multi-platform campaign
  (X ≤ 280 chars); invalid platform; schedule → scheduler publishes due piece → simulated engagement;
  publish now → user-entered performance; learning cycle (stats, rules, run, learner decision) → **next
  piece has `learnings_applied`**; second cycle supersedes the first; learning refuses with < 2 pieces;
  stats endpoint; regenerate; 404s.

### UI (Playwright)

`tests/ui/conftest.py` starts `uvicorn` on a free port with `MESH_MOCK=1`, SQLite, and a 2-second scheduler
poll. Tests, in order:

1. Dashboard loads; seed demo brands; brands page lists both.
2. Create a brand from the form with 2 samples → profile learned.
3. New brief → detail page: status reaches *ready*, final text, **editor diff with insertions**, timeline
   shows strategist/writer/editor/visual/evaluator, required edits, quality number, image.
4. Publish now → record performance via the form → performance table shows a `user` row.
5. Schedule a piece in the past → background scheduler publishes it → status *published* after reload.
6. Learnings page: run a learning cycle → active rules appear with confidence bars.
7. Decision trail page: agent filter works.
8. Example brief for a brand pre-fills brief + platforms; pipeline strip shows every stage done with the editor round badge; agent log shows Mesh model/tokens; schedule modal shows the recommended slot and its reason.
9. Instagram carousel preview navigates slides; raw/preview toggle; replay steps through strategist → editor (stage panel shows required edits, strip marks the active node) and Play runs to the end; LinkedIn preview folds at ~210 chars with *see more*.

## How to run

```bash
pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium            # once
MESH_MOCK=1 pytest tests/unit tests/integration -q
MESH_MOCK=1 pytest tests/ui -q --browser chromium       # add --headed to watch
# or everything in a container:
docker compose -f docker-compose.test.yml run --rm tests
```

## Manual / exploratory checks against real Mesh

| Check | Steps | Expected |
|---|---|---|
| Real editor loop | brief for LinkedIn | ≥1 round, required edits are specific, v2 differs materially, CQS after ≥ before in most cases |
| Brand voice | same brief for *Techsivam Labs* and *Sunny Side Bakes* | bakery output has emoji/hashtags/playful tone; tech output is terse and contrarian |
| Learning | publish ≥3 pieces, enter different metrics, run cycle, regenerate | rules reference the better performers; next strategist decision cites applied learnings |
| Image | any brief | PNG matches the piece; no text in the image |
| Real X publish | set `X_*` env, target `x` | tweet posted, URL stored, metrics refreshed within 30 min |

## Known gaps

- Real-model output quality is non-deterministic; only measured, not asserted.
- Real X publishing is not covered by automated tests (credentials).
