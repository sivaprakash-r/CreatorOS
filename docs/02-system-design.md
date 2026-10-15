# CreatorOS — System Design

## 1. Overview

```
                    ┌────────────────────────── Web UI (app/static) ──────────────────────────┐
                    │ Dashboard · New brief · Content · Brand voices · Learnings · Decisions  │
                    └───────────────────────────────┬─────────────────────────────────────────┘
                                                    │ REST (JSON)
┌───────────────────────────────────────────────────▼──────────────────────────────────────────┐
│ FastAPI  app/main.py  ·  app/api/routes.py                                                   │
│                                                                                              │
│  services/brand ── services/studio (coordinator) ── services/learning ── services/publisher  │
│        │                   │                              │                     │            │
│        │          graph/pipeline.py (LangGraph)           │              scheduler (APS)     │
│        │   strategist → writer → editor ⇄ reviser → visual → finalize           │            │
│        │                   │                              │                     │            │
│        └────────────── agents/*  (one prompt + job each) ─┘                     │            │
│                            │                                                    │            │
│                      app/mesh/client.py  ← the ONLY LLM/AI gateway (Mesh API)   │            │
└────────────────────────────┼────────────────────────────────────────────────────┼────────────┘
                             │ https://api.meshapi.ai/v1                          │
                    chat (gpt-4o-mini…) · images (gpt-image-1) · embeddings       │
                                                                                  ▼
                                 PostgreSQL (SQLAlchemy 2.0) ── data/images/*.png (volume)
```

## 2. Agents (distinct jobs, distinct prompts)

| Agent | Module | Input | Output | Decision logged |
|---|---|---|---|---|
| **Strategist** | `agents/strategist.py` | brief, platform spec, brand profile + measured stats, active learnings, engagement-by-feature table | angle, hook (+type), audience, key points, CTA, format, rejected alternatives, reasoning | `angle_selected` |
| **Writer** | `agents/writer.py` | strategist plan, platform spec, brand voice, learnings | draft + hashtags (`draft`), or revised draft + change log (`revise`) | `draft_written`, `revision_n` |
| **Editor** | `agents/editor.py` | draft, measured facts (chars, hashtags, …), plan, brand voice, learnings, round, pass score | score 0-10, 6 criteria, verdict, praise, issues, numbered required edits | `review_round_n` |
| **Visual** | `agents/visual.py` + `services/poster.py` | final text, angle, brand voice | background-only image prompt, headline, subline, palette → background via Mesh image model → branded poster (chip + typeset headline) | `image_concept` (incl. `image_model_used`, `error`) |
| **Learner** | `agents/learner.py` | engagement per feature table + top/bottom performer texts | rules (`insight`, `rule`, `confidence`, `applies_to`), stop-doing list | `learning_cycle` |
| **Brand analyst** | `agents/brand.py` | ≥2 samples + measured style stats | voice profile JSON | `voice_profile_learned` |
| **Judge** (evaluation only) | `services/quality.py` | text, platform, brand profile | 6 criteria 1-10 — a *different* prompt from the editor's, so the editor is not grading itself | `quality_scored` |

The verdict of the editor is derived deterministically from its score against `EDITOR_PASS_SCORE`
and the platform's hard character limit — an LLM says *how good*, code decides *what happens next*,
which keeps the loop auditable and testable.

## 3. The LangGraph pipeline

```python
g.set_entry_point("strategist")
g.add_edge("strategist", "writer")
g.add_edge("writer", "editor")
g.add_conditional_edges("editor", after_editor, {"reviser": "reviser", "visual": "visual"})
g.add_edge("reviser", "editor")          # ← the loop
g.add_edge("visual", "finalize")
```

State (`ContentState`, a TypedDict) carries the brief, brand context, learnings, the current draft, every
critique, the round counter and the trace. `after_editor` sends the draft back to the reviser while the
verdict is `revise`; the editor itself caps the loop at `EDITOR_MAX_ROUNDS` revisions (verdict
`accept_max_rounds`, recorded as such). Every node writes to a `Sink`:
`DbSink` in production (own short DB sessions so the UI can poll progress), `ListSink` in tests.

## 4. Brand voice

1. User supplies ≥2 past pieces (`brand_samples`).
2. `services/features.style_stats` measures them: avg chars, words/sentence, emoji per post, hashtags per
   post, list usage, hook-type distribution.
3. The brand agent (Mesh) produces a profile: tone, persona, sentence style, vocabulary, signature moves,
   do / don't, emoji policy, formatting.
4. `agents/context.brand_block` renders profile + stats into every strategist / writer / editor / visual
   prompt. The editor scores `brand_voice_fit` explicitly, and the judge uses embedding similarity to the
   brand's samples (`voice_similarity`) as 25 % of CQS.

## 5. The performance feedback loop (the core)

```
publish ──► performance (real | user | simulated) ──► run_learning(brand, platform)
                                                           │
            ┌──────────────────────────────────────────────┘
            ▼
   1. feature_stats(): mean engagement per feature value (hook_type, length_bucket, has_list, has_cta,
      has_numbers, first_person, emoji, hashtags) → LearningRun.stats
   2. learner agent: stats + top/bottom texts → rules with confidence → Learning rows (previous cycle
      deactivated, kept for audit)
            │
            ▼
   next generate_piece(): active_learnings() + latest_perf_stats() are injected into
   strategist / writer / editor prompts; the piece records learnings_applied = [ids]
```

Engagement score = `(likes + 4·comments + 5·shares + 3·saves + 2·clicks) / impressions / 0.5`, clipped to 1
(absolute fallback when impressions are unknown). Sources: `platform` (X API), `user` (form), `simulated`
(`simulate_metrics`, a transparent noisy model that rewards hooks, CTAs, concreteness and structure).

**Provable change:** Experiment B in `scripts/evaluate.py` generates the same briefs before and after a
learning cycle and reports CQS, engagement under the same model, and the feature shift in the output.

## 6. Quality measure (self-evaluation)

`CQS = 25·platform_fit + 25·voice_similarity + 50·judge_score` (0-100), see `services/quality.py`:

- `platform_fit` — 7 rule checks against the platform spec (hard limit, ideal window, hook before the fold,
  hashtag budget, CTA, URL spam, structure), weighted.
- `voice_similarity` — cosine between the piece's embedding and the centroid of the brand's samples
  (embeddings via Mesh), rescaled.
- `judge_score` — LLM judge, six criteria 1-10, temperature 0.

Scored on the first draft and on the final draft of every piece (`quality_before`, `quality_after`).

## 7. Data model

```
brands(id, name, description, profile JSON, profile_stats JSON)
brand_samples(id, brand_id, text, platform)
content_pieces(id, brand_id, campaign_id, brief, platform, status, strategy JSON, final_text, hashtags,
               editor_rounds, final_editor_score, quality_before, quality_after, learnings_applied JSON,
               image_path, image_prompt, alt_text, scheduled_at, published_at, publish_target,
               external_id, external_url, error)
content_versions(id, content_id, version, source, text, hashtags, editor_score, critique JSON, quality_score)
decisions(id, content_id?, brand_id?, agent, decision_type, summary, reasoning, payload JSON)
performance(id, content_id, source, impressions, likes, comments, shares, clicks, saves, engagement_score)
learnings(id, brand_id, platform, applies_to, insight, rule, confidence, evidence JSON, active, run_id)
learning_runs(id, brand_id, platform, pieces_analysed, stats JSON, summary)
```

Status lifecycle: `generating:<node>` → `ready` → `scheduled` → `published` (or `failed`).

## 8. Platforms

`app/platforms.py` defines LinkedIn, X, Instagram and Blog specs (hard limit, ideal window, hashtag budget,
conventions, image size). A brief with several platforms creates one piece per platform under one
`campaign_id`; each piece runs the full pipeline with its own platform spec, so the X version is a
≤280-char single post and the LinkedIn version has a hook before the ~210-char fold.

## 9. Scheduling & publishing

`services/scheduling.py::recommend_slot` proposes a publish time: the best-performing hour of the brand's published posts on that platform (≥3 with metrics), otherwise platform defaults — with the reason, which is stored on the `scheduled` decision.

APScheduler (`BackgroundScheduler`) polls every `SCHEDULER_POLL_SECONDS` for `scheduled` pieces whose
`scheduled_at` ≤ now and publishes them; every 30 min it refreshes metrics of pieces posted through X.
Publish targets: `simulated` (default; synthesises engagement if `SIMULATE_ENGAGEMENT=1`) and `x` (real,
needs `X_*` credentials). Other platforms fall back to simulated and the decision trail says so.

## 10. Mesh API gateway

`app/mesh/client.py` wraps the OpenAI SDK with `base_url=https://api.meshapi.ai/v1` and `MESH_API_KEY`.
It exposes `chat`, `chat_json` (JSON mode + fence-tolerant parsing), `generate_image`, `embed`, records each
call (`LLMCall`: task, model, tokens, latency) and raises at startup if the key is missing. Models are
configurable per role (`MESH_CHAT_MODEL`, `MESH_EDITOR_MODEL`, `MESH_IMAGE_MODEL`, `MESH_EMBEDDING_MODEL`).
`MESH_MOCK=1` substitutes deterministic canned responses for offline tests only; the UI footer shows a red
"MOCK MODE" label when it is on.

## 11. Failure handling

- Pipeline exceptions mark the piece `failed` with the error; the UI shows it and offers regenerate.
- Image generation is best-effort: on failure the prompt is kept and the decision says so.
- Quality scoring never blocks delivery.
- Publishing errors mark the piece `failed` without losing the content.
