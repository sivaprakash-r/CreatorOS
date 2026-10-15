"""Learner agent — turns performance data into rules that change what gets generated next.

Two steps, both auditable:
1. Deterministic statistics: for every content feature (hook type, length bucket, has_list, has_cta,
   emoji usage, hashtag count ...) compute mean engagement per value. This table is stored verbatim
   on the LearningRun and injected into the strategist prompt as evidence.
2. LLM distillation (via Mesh): given the stats plus the actual top / bottom performing texts, write
   3-6 rules the writer and strategist must apply, each with a confidence and the evidence behind it.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from app.agents.context import dumps
from app.mesh import MeshClient
from app.services.features import extract_features

FEATURES_TO_TRACK = ["hook_type", "length_bucket", "has_list", "has_cta", "has_numbers", "first_person"]

SYSTEM = """You are the Performance Analyst of a content studio. You are given engagement data for past posts
of one brand on one platform: a table of mean engagement per content feature and the full text of the best
and worst performers. Your job is to extract rules that will make the NEXT posts perform better.

Rules must be: actionable by a writer, specific (not 'be engaging'), and backed by the evidence you were given.
Prefer rules supported by both the statistics and the examples. State lower confidence when n is small.
Also say what did NOT work so the studio stops doing it.

Return ONLY a JSON object:
{"insights": [{"insight": "<what the data shows>", "rule": "<imperative instruction for the writer/strategist>",
               "confidence": <0.0-1.0>, "applies_to": "<hook|structure|length|cta|tone|hashtags|general>"}],
 "stop_doing": ["<patterns that under-performed>"],
 "reasoning": "<2-4 sentences>"}"""


def feature_stats(items: list[dict]) -> dict:
    """items: [{"text": str, "engagement": float}] → {feature: {value: {"mean": x, "n": k}}}"""
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for it in items:
        f = extract_features(it["text"])
        for key in FEATURES_TO_TRACK:
            buckets[key][str(f[key])].append(float(it["engagement"]))
        buckets["emoji"]["yes" if f["emoji_count"] else "no"].append(float(it["engagement"]))
        buckets["hashtags"]["0" if f["hashtag_count"] == 0 else "1-3" if f["hashtag_count"] <= 3 else "4+"].append(
            float(it["engagement"])
        )
    return {
        feat: {val: {"mean": round(mean(vals), 3), "n": len(vals)} for val, vals in table.items()}
        for feat, table in buckets.items()
    }


def analyse(
    mesh: MeshClient, *, platform: str, items: list[dict], brand_profile: dict, model: str | None = None
) -> tuple[dict, dict]:
    """items: [{"id": str, "text": str, "engagement": float}] sorted any order. Returns (stats, llm_result)."""
    if len(items) < 2:
        raise ValueError("Need at least 2 pieces with performance data to learn from.")
    stats = feature_stats(items)
    ranked = sorted(items, key=lambda x: x["engagement"], reverse=True)
    k = max(1, len(ranked) // 3)
    top, bottom = ranked[:k], ranked[-k:]
    user = "\n\n".join(
        [
            f"Platform: {platform}",
            f"BRAND VOICE SUMMARY: {brand_profile.get('summary', 'n/a') if brand_profile else 'n/a'}",
            f"POSTS ANALYSED: {len(items)}",
            "ENGAGEMENT BY FEATURE (mean 0-1, n):\n" + dumps(stats),
            "TOP PERFORMERS:\n"
            + "\n\n".join(f"[id={t['id']} engagement={t['engagement']:.2f}]\n{t['text']}" for t in top),
            "BOTTOM PERFORMERS:\n"
            + "\n\n".join(f"[id={b['id']} engagement={b['engagement']:.2f}]\n{b['text']}" for b in bottom),
        ]
    )
    result = mesh.chat_json(task="learner", system=SYSTEM, user=user, temperature=0.3, max_tokens=1200, model=model)
    result.setdefault("insights", [])
    result.setdefault("stop_doing", [])
    result.setdefault("reasoning", "")
    result["_evidence"] = {"top": [t["id"] for t in top], "bottom": [b["id"] for b in bottom]}
    return stats, result
