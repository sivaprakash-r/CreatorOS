"""Self-evaluation: does CreatorOS actually improve content?

Three experiments, all scored with the same Content Quality Score (app/services/quality.py):

  A. Editor loop      — CQS of the first draft vs. the draft after the editor/writer loop.
  B. Learning loop    — the same briefs generated (1) with no learnings and (2) after a learning cycle
                        on published performance. Compares CQS *and* engagement under the same
                        engagement model, and checks that the learned rules are visible in the output.
  C. Brand voice      — the same brief for two different brands; voice-similarity of each output to
                        its own brand's samples vs. the other brand's samples.

Usage (real Mesh — costs a few cents):
    python scripts/evaluate.py --briefs 4 --platforms linkedin,x
Offline / CI smoke run (deterministic mock responses, numbers are NOT meaningful):
    MESH_MOCK=1 python scripts/evaluate.py --briefs 2

Writes eval/results.json and eval/results.md (both committed to the repo).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_BRIEFS = [
    "a LinkedIn post about AI safety for engineering leaders",
    "why most Kubernetes cost-cutting advice is wrong",
    "lessons from running an LLM gateway in production for 90 days",
    "how small teams should think about observability",
    "what I learned shipping a feature on Friday and breaking it on Saturday",
    "the trade-off between speed and reliability in deploys",
]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", type=int, default=4)
    ap.add_argument("--platforms", default="linkedin,x")
    ap.add_argument("--db", default=str(ROOT / "eval" / "eval.db"))
    ap.add_argument("--out", default=str(ROOT / "eval"))
    ap.add_argument("--images", action="store_true", help="also generate images (slower, costs more)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("SCHEDULER_ENABLED", "0")

    from app.config import get_settings
    from app.db import init_db, session_scope
    from app.mesh import get_mesh_client
    from app.models import Brand, ContentPiece
    from app.services import brand as brand_service
    from app.services import learning as learning_service
    from app.services import publisher, studio
    from app.services.demo import DEMO_BRANDS
    from app.services.features import extract_features
    from app.services.quality import score_content, voice_similarity

    settings = get_settings()
    mesh = get_mesh_client()
    init_db()
    mode = "MOCK (numbers not meaningful)" if settings.mesh_mock else f"Mesh API · {settings.mesh_chat_model}"
    print(f"== CreatorOS self-evaluation · {mode}")
    t0 = time.time()

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    briefs = DEFAULT_BRIEFS[: args.briefs]

    # ---------------------------------------------------------------- brands
    with session_scope() as db:
        brands = {}
        for spec in DEMO_BRANDS:
            b = brand_service.create_brand(db, name=spec["name"], description=spec["description"])
            brand_service.add_samples(db, b, spec["samples"])
            db.refresh(b)
            brand_service.learn_profile(db, mesh, b)
            brands[spec["name"]] = b.id
    tech_id = brands["Techsivam Labs"]
    bakery_id = brands["Sunny Side Bakes"]
    print(f"-- learned {len(brands)} brand voices")

    def generate(brand_id: str, brief: str, platform: str, use_learnings: bool) -> ContentPiece:
        with session_scope() as db:
            brand = db.get(Brand, brand_id)
            piece = studio.create_piece(db, brand=brand, brief=brief, platform=platform)
            pid = piece.id
        return studio.generate_piece(pid, use_learnings=use_learnings, generate_image=args.images)

    # ------------------------------------------- A + B(baseline): no learnings
    baseline: list[ContentPiece] = []
    for brief in briefs:
        for platform in platforms:
            p = generate(tech_id, brief, platform, use_learnings=False)
            baseline.append(p)
            print(f"   baseline {platform:9s} rounds={p.editor_rounds} CQS {p.quality_before} -> {p.quality_after}  '{brief[:40]}'")

    exp_a = {
        "pieces": len(baseline),
        "cqs_first_draft_mean": mean([p.quality_before for p in baseline]),
        "cqs_after_editor_mean": mean([p.quality_after for p in baseline]),
        "improved_count": sum(1 for p in baseline if (p.quality_after or 0) > (p.quality_before or 0)),
        "unchanged_text_count": sum(1 for p in baseline if len(p.versions) < 2),
        "mean_editor_rounds": mean([p.editor_rounds for p in baseline]),
        "per_piece": [
            {"brief": p.brief, "platform": p.platform, "rounds": p.editor_rounds, "before": p.quality_before, "after": p.quality_after,
             "first_draft_chars": len(p.versions[0].text) if p.versions else None, "final_chars": len(p.final_text)}
            for p in baseline
        ],
    }
    exp_a["cqs_delta_mean"] = round((exp_a["cqs_after_editor_mean"] or 0) - (exp_a["cqs_first_draft_mean"] or 0), 2)

    # ---------------------------------------------------- B: feedback + learn
    with session_scope() as db:
        for p in baseline:
            piece = db.get(ContentPiece, p.id)
            publisher.publish(db, piece)  # simulated publish → simulated engagement captured
    with session_scope() as db:
        brand = db.get(Brand, tech_id)
        runs = {}
        for platform in platforms:
            run = learning_service.run_learning(db, mesh, brand, platform=platform)
            runs[platform] = {"run_id": run.id, "pieces": run.pieces_analysed, "summary": run.summary}
        rules = {platform: learning_service.active_learnings(db, tech_id, platform) for platform in platforms}
    print(f"-- learning cycle: {sum(len(v) for v in rules.values())} rules learned")

    learned: list[ContentPiece] = []
    for brief in briefs:
        for platform in platforms:
            p = generate(tech_id, brief, platform, use_learnings=True)
            learned.append(p)
            print(f"   learned  {platform:9s} rounds={p.editor_rounds} CQS {p.quality_before} -> {p.quality_after}  applied={len(p.learnings_applied)}")

    def eng(p: ContentPiece) -> float:
        return learning_service.engagement_score(learning_service.simulate_metrics(p.final_text, seed=p.id))

    base_eng = [eng(p) for p in baseline]
    learn_eng = [eng(p) for p in learned]
    exp_b = {
        "rules": rules,
        "learning_runs": runs,
        "baseline_cqs_mean": mean([p.quality_after for p in baseline]),
        "with_learnings_cqs_mean": mean([p.quality_after for p in learned]),
        "baseline_engagement_mean": round(statistics.mean(base_eng), 3),
        "with_learnings_engagement_mean": round(statistics.mean(learn_eng), 3),
        "pieces_with_learnings_applied": sum(1 for p in learned if p.learnings_applied),
        "feature_shift": {},
        "note": "Engagement for both sets is computed with the same engagement model (app/services/learning.py::simulate_metrics) "
        "so that the comparison is fair; with real platform metrics the same table is produced from the platform data.",
    }
    for key in ("hook_type", "has_cta", "has_numbers", "has_list", "length_bucket"):
        exp_b["feature_shift"][key] = {
            "baseline": _dist([extract_features(p.final_text)[key] for p in baseline]),
            "with_learnings": _dist([extract_features(p.final_text)[key] for p in learned]),
        }
    exp_b["cqs_delta"] = round((exp_b["with_learnings_cqs_mean"] or 0) - (exp_b["baseline_cqs_mean"] or 0), 2)
    exp_b["engagement_delta"] = round(exp_b["with_learnings_engagement_mean"] - exp_b["baseline_engagement_mean"], 3)

    # ------------------------------------------------------- C: brand voice
    brief = briefs[0]
    platform = platforms[0]
    tech_piece = generate(tech_id, brief, platform, use_learnings=False)
    bakery_piece = generate(bakery_id, brief, platform, use_learnings=False)
    with session_scope() as db:
        tech_samples = [s.text for s in db.get(Brand, tech_id).samples]
        bakery_samples = [s.text for s in db.get(Brand, bakery_id).samples]
    sim = {
        "tech_output_vs_tech_samples": voice_similarity(mesh, tech_piece.final_text, tech_samples),
        "tech_output_vs_bakery_samples": voice_similarity(mesh, tech_piece.final_text, bakery_samples),
        "bakery_output_vs_bakery_samples": voice_similarity(mesh, bakery_piece.final_text, bakery_samples),
        "bakery_output_vs_tech_samples": voice_similarity(mesh, bakery_piece.final_text, tech_samples),
    }
    exp_c = {
        "brief": brief,
        "platform": platform,
        "voice_similarity": sim,
        "own_voice_wins": sim["tech_output_vs_tech_samples"] > sim["tech_output_vs_bakery_samples"]
        and sim["bakery_output_vs_bakery_samples"] > sim["bakery_output_vs_tech_samples"],
        "tech_features": extract_features(tech_piece.final_text),
        "bakery_features": extract_features(bakery_piece.final_text),
        "tech_text": tech_piece.final_text,
        "bakery_text": bakery_piece.final_text,
    }

    # ------------------------------------------------------------- report
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "chat_model": settings.mesh_chat_model,
        "editor_model": settings.mesh_editor_model,
        "briefs": briefs,
        "platforms": platforms,
        "quality_measure": "CQS = 25*platform_fit + 25*voice_similarity + 50*llm_judge (0-100); see app/services/quality.py",
        "experiment_a_editor_loop": exp_a,
        "experiment_b_learning_loop": exp_b,
        "experiment_c_brand_voice": exp_c,
        "mesh_calls": len(mesh.calls),
        "seconds": round(time.time() - t0, 1),
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "results.md").write_text(render_md(results), encoding="utf-8")
    print(render_md(results))
    print(f"-- wrote {out_dir / 'results.json'} and {out_dir / 'results.md'} ({results['mesh_calls']} Mesh calls, {results['seconds']}s)")
    return 0


def _dist(values) -> dict:
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def render_md(r: dict) -> str:
    a, b, c = r["experiment_a_editor_loop"], r["experiment_b_learning_loop"], r["experiment_c_brand_voice"]
    lines = [
        f"# Self-evaluation results",
        "",
        f"Generated {r['generated_at']} · mode: **{r['mode']}** · {r['mesh_calls']} Mesh calls · {r['seconds']}s",
        "",
        f"Quality measure: `{r['quality_measure']}`",
        "",
        "## A. Editor refinement loop (first draft → after editor)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| pieces | {a['pieces']} |",
        f"| mean CQS, first draft | **{a['cqs_first_draft_mean']}** |",
        f"| mean CQS, after editor loop | **{a['cqs_after_editor_mean']}** |",
        f"| mean delta | **{a['cqs_delta_mean']:+}** |",
        f"| pieces improved | {a['improved_count']} / {a['pieces']} |",
        f"| pieces whose text did not change | {a['unchanged_text_count']} |",
        f"| mean editor rounds | {a['mean_editor_rounds']} |",
        "",
        "| brief | platform | rounds | before | after |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {p['brief'][:50]} | {p['platform']} | {p['rounds']} | {p['before']} | {p['after']} |" for p in a["per_piece"]]
    lines += [
        "",
        "## B. Performance feedback loop (no learnings → after one learning cycle)",
        "",
        "| metric | baseline | with learnings | delta |",
        "|---|---|---|---|",
        f"| mean CQS (after editor) | {b['baseline_cqs_mean']} | {b['with_learnings_cqs_mean']} | {b['cqs_delta']:+} |",
        f"| mean engagement (same engagement model) | {b['baseline_engagement_mean']} | {b['with_learnings_engagement_mean']} | {b['engagement_delta']:+} |",
        f"| pieces that had learnings injected | 0 | {b['pieces_with_learnings_applied']} | |",
        "",
        "Rules learned:",
        "",
    ]
    for platform, rules in b["rules"].items():
        for rule in rules:
            lines.append(f"- **[{platform} / {rule['applies_to']} / conf {rule['confidence']:.2f}]** {rule['rule']} — _{rule['insight']}_")
    lines += ["", "Feature shift in the generated output (counts):", ""]
    for key, v in b["feature_shift"].items():
        lines.append(f"- `{key}`: baseline {v['baseline']} → with learnings {v['with_learnings']}")
    lines += [
        "",
        f"_{b['note']}_",
        "",
        "## C. Brand voice (same brief, two brands)",
        "",
        f"Brief: _{c['brief']}_ · platform: {c['platform']}",
        "",
        "| output | vs Techsivam samples | vs Sunny Side samples |",
        "|---|---|---|",
        f"| Techsivam output | **{c['voice_similarity']['tech_output_vs_tech_samples']}** | {c['voice_similarity']['tech_output_vs_bakery_samples']} |",
        f"| Sunny Side output | {c['voice_similarity']['bakery_output_vs_tech_samples']} | **{c['voice_similarity']['bakery_output_vs_bakery_samples']}** |",
        "",
        f"Each output is closest to its own brand: **{c['own_voice_wins']}**. "
        f"Emoji count: Techsivam {c['tech_features']['emoji_count']} vs Sunny Side {c['bakery_features']['emoji_count']}; "
        f"hashtags: {c['tech_features']['hashtag_count']} vs {c['bakery_features']['hashtag_count']}.",
        "",
        "<details><summary>Techsivam output</summary>",
        "",
        "```",
        c["tech_text"],
        "```",
        "</details>",
        "<details><summary>Sunny Side output</summary>",
        "",
        "```",
        c["bakery_text"],
        "```",
        "</details>",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
