"""Writer agent — drafts for the exact platform in the brand voice, and revises on editor feedback."""

from __future__ import annotations

from app.agents.context import brand_block, dumps, learnings_block, platform_block
from app.mesh import MeshClient

SYSTEM_DRAFT = """You are the Writer of a content studio. You write ONE finished piece for ONE platform,
following the strategist's plan exactly (angle, hook as the first line, key points, CTA) and the brand voice
profile. Apply every performance learning you are given — they are evidence, not suggestions.
Respect the platform's hard character limit and conventions. Do not add a title unless the platform is a blog.
Hashtags go in the separate field, not inside the text (except for blog: none).

Return ONLY a JSON object:
{"draft": "<the full text, with real line breaks>", "hashtags": ["<without spaces, with #>"],
 "notes": "<one sentence on how you applied the voice and learnings>"}"""

SYSTEM_REVISE = """You are the Writer of a content studio revising your own draft after an editor's critique.
Make every required edit the editor asked for, keep what the editor praised, stay inside the platform's
limits and the brand voice. The result must be a genuinely improved piece, not a cosmetic rewrite — but do not
throw away the structure the strategist chose. Keep the hook unless the editor asked to change it.

Return ONLY a JSON object:
{"draft": "<the full revised text>", "hashtags": ["..."],
 "change_log": ["<each concrete change you made, mapped to the editor's request>"]}"""


def draft(
    mesh: MeshClient,
    *,
    brief: str,
    platform: str,
    strategy: dict,
    brand_profile: dict,
    brand_stats: dict,
    learnings: list[dict],
    model: str | None = None,
) -> dict:
    user = "\n\n".join(
        [
            f"Brief: {brief}",
            f"Platform: {platform}",
            platform_block(platform),
            brand_block(brand_profile, brand_stats),
            learnings_block(learnings),
            "STRATEGIST PLAN:\n" + dumps({k: v for k, v in strategy.items() if not k.startswith("_")}),
        ]
    )
    result = mesh.chat_json(task="writer", system=SYSTEM_DRAFT, user=user, temperature=0.8, max_tokens=2500, model=model)
    result["draft"] = str(result.get("draft", "")).strip()
    result["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in result.get("hashtags", []) if h]
    return result


def revise(
    mesh: MeshClient,
    *,
    platform: str,
    current_draft: str,
    critique: dict,
    strategy: dict,
    brand_profile: dict,
    learnings: list[dict],
    model: str | None = None,
) -> dict:
    user = "\n\n".join(
        [
            f"Platform: {platform}",
            platform_block(platform),
            brand_block(brand_profile),
            learnings_block(learnings),
            "STRATEGIST PLAN (keep the angle):\n" + dumps({k: strategy.get(k) for k in ("angle", "hook", "cta")}),
            "CURRENT DRAFT:\n" + current_draft,
            "EDITOR CRITIQUE:\n" + dumps({k: critique.get(k) for k in ("score", "criteria", "issues", "required_edits", "praise")}),
        ]
    )
    result = mesh.chat_json(task="writer_revise", system=SYSTEM_REVISE, user=user, temperature=0.6, max_tokens=2500, model=model)
    result["draft"] = str(result.get("draft", "")).strip()
    result["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in result.get("hashtags", []) if h]
    result.setdefault("change_log", [])
    return result
