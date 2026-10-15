# CreatorOS — Self-Evaluation

## The quality measure: Content Quality Score (CQS, 0–100)

```
CQS = 25 · platform_fit + 25 · voice_similarity + 50 · judge_score
```

| Component | How it is computed | Why |
|---|---|---|
| `platform_fit` (0–1) | 7 weighted rule checks from `app/platforms.py`: hard limit (0.25), ideal length window (0.15), hook before the fold (0.20), hashtag budget (0.10), CTA present (0.15), no URL spam (0.05), structure (0.10) | deterministic, platform-specific, cheap |
| `voice_similarity` (0–1) | cosine between the embedding of the piece and the centroid of the brand's sample embeddings (Mesh `text-embedding-3-small`), rescaled from the 0.30–0.95 band | measures "sounds like the brand" independently of the LLM judge |
| `judge_score` (0–1) | LLM judge via Mesh, temperature 0, six criteria 1–10 (hook, clarity, specificity, brand-voice fit, platform fit, CTA), averaged | semantic quality; prompt is different from the editor's, so the editor is not grading itself |

Implementation: `app/services/quality.py`. Every generated piece is scored twice (first draft and final
draft) and both numbers are stored (`quality_before`, `quality_after`) and shown in the UI.

## The script

`scripts/evaluate.py` builds a fresh database, learns both demo brand voices, then runs three experiments
and writes `eval/results.json` + `eval/results.md`:

| Experiment | Question | Method |
|---|---|---|
| **A. Editor loop** | Does the critique → revise loop improve drafts? | For N briefs × platforms: CQS of the first draft vs. the draft after the loop; also counts pieces whose text did not change (must be 0) |
| **B. Learning loop** | Does feedback change — and improve — future output? | Generate all briefs with **no** learnings → publish → capture engagement → run a learning cycle → generate the **same briefs again** with learnings. Compare CQS, engagement under the same engagement model, and the feature distribution (hook type, CTA, numbers, lists, length) of the output. Also verifies the learnings were actually injected (`learnings_applied`). |
| **C. Brand voice** | Do different brand profiles produce visibly different output? | Same brief for *Techsivam Labs* and *Sunny Side Bakes*; voice-similarity matrix (each output vs. each brand's samples) plus emoji/hashtag counts |

Run it (costs a few cents; ~3–5 minutes with `gpt-4o-mini`):

```bash
python scripts/evaluate.py --briefs 4 --platforms linkedin,x
```

## Results

> **Status:** the numbers committed in `eval/results.md` come from a **mock-mode smoke run**
> (`MESH_MOCK=1`, deterministic canned responses) that proves the harness works end-to-end. They are
> **not** a measurement of model quality. Run the command above with a real `MESH_API_KEY` and replace this
> section (and the README table) with the real numbers before submitting.

Headline table to fill in from `eval/results.md`:

| Experiment | Metric | Baseline | After | Delta |
|---|---|---|---|---|
| A | mean CQS, first draft → after editor | | | |
| A | pieces improved / total | | | |
| B | mean CQS without → with learnings | | | |
| B | mean engagement without → with learnings (same model) | | | |
| C | own-voice similarity > cross-voice similarity for both brands | | | true / false |

Mock-run sanity values (for reference only): editor delta **+3.6 CQS**, 6/6 pieces improved, 0 unchanged
texts, 4 rules learned and injected into 6/6 follow-up pieces.

## Honest caveats

- Experiment B's engagement numbers use the simulator for both arms. The simulator rewards exactly the kind
  of features the learner can discover, so a positive delta shows the loop **works mechanically** (signal
  found → rule written → output shifted); with real platform metrics the same pipeline runs unchanged.
- LLM-judge scores carry noise of roughly ±0.5 per criterion at temperature 0; with 8 pieces the mean delta
  is indicative, not statistically significant. The per-piece table is included so the spread is visible.
- Voice similarity uses the brand's own samples as the reference, so a brand with few samples has a noisier
  centroid.
