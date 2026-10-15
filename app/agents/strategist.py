"""Strategist agent — decides the angle, hook, audience and structure before a word is written."""

from __future__ import annotations

from app.agents.context import brand_block, dumps, learnings_block, platform_block
from app.mesh import MeshClient

SYSTEM = """You are the Content Strategist of a content studio. You do NOT write the post.
Your job is to decide, for a given brief, platform and brand, the single best angle to take and to
explain why. You weigh three inputs: the brief, the brand voice profile, and the performance learnings
(evidence about what has actually worked for this brand). When learnings exist they beat your priors —
say explicitly which learning you applied.

Return ONLY a JSON object:
{
 "angle": "<one sentence: the specific take / thesis>",
 "hook": "<the exact first line to open with>",
 "hook_type": "<question|statistic|contrarian|story|list|statement>",
 "audience": "<who precisely this is for>",
 "key_points": ["<3-5 concrete points, each specific enough to write from>"],
 "cta": "<what the reader should do at the end>",
 "format": "<structure guidance for the writer, e.g. '3 short paragraphs + 4-item list'>",
 "alternatives_rejected": ["<one or two other angles you considered and why you rejected them>"],
 "learnings_applied": ["<ids or rules you applied, or empty>"],
 "reasoning": "<2-4 sentences: why this angle, hook and audience>"
}"""


def run(
    mesh: MeshClient,
    *,
    brief: str,
    platform: str,
    brand_profile: dict,
    brand_stats: dict,
    learnings: list[dict],
    perf_stats: dict | None,
    model: str | None = None,
) -> dict:
    user = "\n\n".join(
        [
            f"Brief: {brief}",
            f"Platform: {platform}",
            platform_block(platform),
            brand_block(brand_profile, brand_stats),
            learnings_block(learnings, perf_stats),
        ]
    )
    result = mesh.chat_json(task="strategist", system=SYSTEM, user=user, temperature=0.6, model=model)
    result.setdefault("key_points", [])
    result.setdefault("reasoning", "")
    result["_prompt_excerpt"] = dumps({"learnings_in_prompt": [lr.get("rule") for lr in learnings]})
    return result
