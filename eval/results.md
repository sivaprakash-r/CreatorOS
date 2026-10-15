# Self-evaluation results

Generated 2026-10-15T17:11:22.017597+00:00 · mode: **MOCK (numbers not meaningful)** · 148 Mesh calls · 0.9s

Quality measure: `CQS = 25*platform_fit + 25*voice_similarity + 50*llm_judge (0-100); see app/services/quality.py`

## A. Editor refinement loop (first draft → after editor)

| metric | value |
|---|---|
| pieces | 6 |
| mean CQS, first draft | **68.4** |
| mean CQS, after editor loop | **72.03** |
| mean delta | **+3.63** |
| pieces improved | 6 / 6 |
| pieces whose text did not change | 0 |
| mean editor rounds | 2 |

| brief | platform | rounds | before | after |
|---|---|---|---|---|
| a LinkedIn post about AI safety for engineering le | linkedin | 2 | 71.9 | 76.0 |
| a LinkedIn post about AI safety for engineering le | x | 2 | 65.0 | 69.2 |
| why most Kubernetes cost-cutting advice is wrong | linkedin | 2 | 70.9 | 74.9 |
| why most Kubernetes cost-cutting advice is wrong | x | 2 | 63.8 | 68.4 |
| lessons from running an LLM gateway in production  | linkedin | 2 | 71.1 | 75.2 |
| lessons from running an LLM gateway in production  | x | 2 | 67.7 | 68.5 |

## B. Performance feedback loop (no learnings → after one learning cycle)

| metric | baseline | with learnings | delta |
|---|---|---|---|
| mean CQS (after editor) | 72.03 | 72.03 | +0.0 |
| mean engagement (same engagement model) | 0.602 | 0.584 | -0.018 |
| pieces that had learnings injected | 0 | 6 | |

Rules learned:

- **[linkedin / hook / conf 0.70]** Prefer a contrarian or bold-claim opening line. — _Contrarian hooks out-perform question hooks for this audience._
- **[linkedin / cta / conf 0.60]** End with one specific, time-bound action. — _Posts with a concrete time-bound takeaway earn more comments._
- **[x / hook / conf 0.70]** Prefer a contrarian or bold-claim opening line. — _Contrarian hooks out-perform question hooks for this audience._
- **[x / cta / conf 0.60]** End with one specific, time-bound action. — _Posts with a concrete time-bound takeaway earn more comments._

Feature shift in the generated output (counts):

- `hook_type`: baseline {'contrarian': 2, 'statistic': 4} → with learnings {'contrarian': 2, 'statistic': 4}
- `has_cta`: baseline {'True': 6} → with learnings {'True': 6}
- `has_numbers`: baseline {'True': 6} → with learnings {'True': 6}
- `has_list`: baseline {'True': 3, 'False': 3} → with learnings {'True': 3, 'False': 3}
- `length_bucket`: baseline {'medium': 3, 'short': 3} → with learnings {'medium': 3, 'short': 3}

_Engagement for both sets is computed with the same engagement model (app/services/learning.py::simulate_metrics) so that the comparison is fair; with real platform metrics the same table is produced from the platform data._

## C. Brand voice (same brief, two brands)

Brief: _a LinkedIn post about AI safety for engineering leaders_ · platform: linkedin

| output | vs Techsivam samples | vs Sunny Side samples |
|---|---|---|
| Techsivam output | **0.625** | 0.576 |
| Sunny Side output | 0.625 | **0.576** |

Each output is closest to its own brand: **False**. Emoji count: Techsivam 0 vs Sunny Side 0; hashtags: 0 vs 0.

<details><summary>Techsivam output</summary>

```
Most teams get a LinkedIn post about AI safety for engineering leaders wrong. Here's what actually works.

Everyone *says* they care about a LinkedIn post about AI safety for engineering leaders, but the usual advice stops at slogans. In practice three things matter:

1. Make the goal measurable.
2. Ship small and review often.
3. Write the decision down.

Which of these do you already do?

Takeaway: pick one of the three, measure it for 30 days, and share the result.
```
</details>
<details><summary>Sunny Side output</summary>

```
Most teams get a LinkedIn post about AI safety for engineering leaders wrong. Here's what actually works.

Everyone *says* they care about a LinkedIn post about AI safety for engineering leaders, but the usual advice stops at slogans. In practice three things matter:

1. Make the goal measurable.
2. Ship small and review often.
3. Write the decision down.

Which of these do you already do?

Takeaway: pick one of the three, measure it for 30 days, and share the result.
```
</details>
