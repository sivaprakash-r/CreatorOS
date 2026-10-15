"""Editor agent — critiques a draft against concrete criteria and decides accept / revise."""

from __future__ import annotations

from app.agents.context import brand_block, dumps, learnings_block, platform_block
from app.mesh import MeshClient
from app.services.features import extract_features

SYSTEM = """You are the Editor of a content studio. You are demanding. You score the draft on six concrete
criteria from 1 to 10 and you decide whether it ships. You never rewrite the draft yourself — you tell the
writer precisely what to change, as a numbered list of required edits that can be verified.

Criteria:
1. hook_strength — first line stops the scroll and is specific to the angle
2. clarity — one idea per paragraph, no filler, no jargon stacking
3. specificity — concrete examples, numbers, named trade-offs; generic advice scores <= 4
4. brand_voice_fit — tone, sentence style, do/don't list, emoji policy of the brand profile
5. platform_fit — the limits and conventions given (length window, hashtag budget, fold)
6. cta_quality — a natural, specific closing action or question (matches the strategist's CTA)

You are also given measured facts about the draft (character count etc.). Treat a hard-limit violation as an
automatic 'revise'. Overall score = weighted mean (specificity and hook count double).

Return ONLY a JSON object:
{"score": <0-10 with one decimal>,
 "criteria": {"hook_strength": n, "clarity": n, "specificity": n, "brand_voice_fit": n, "platform_fit": n, "cta_quality": n},
 "verdict": "accept" | "revise",
 "praise": ["<what must be kept>"],
 "issues": ["<specific problems, quoting the draft where useful>"],
 "required_edits": ["<numbered, verifiable edit instructions>"],
 "reasoning": "<2-3 sentences explaining the verdict>"}"""


def critique(
    mesh: MeshClient,
    *,
    platform: str,
    draft: str,
    strategy: dict,
    brand_profile: dict,
    learnings: list[dict],
    round_no: int,
    pass_score: float,
    model: str | None = None,
) -> dict:
    facts = extract_features(draft)
    user = "\n\n".join(
        [
            f"Platform: {platform}",
            platform_block(platform),
            brand_block(brand_profile),
            learnings_block(learnings),
            "STRATEGIST PLAN:\n" + dumps({k: strategy.get(k) for k in ("angle", "hook", "audience", "key_points", "cta")}),
            f"REVIEW ROUND: {round_no}. Accept only if score >= {pass_score}.",
            "MEASURED FACTS: " + dumps(facts),
            "DRAFT:\n" + draft,
        ]
    )
    result = mesh.chat_json(task="editor", system=SYSTEM, user=user, temperature=0.2, max_tokens=1200, model=model)
    try:
        result["score"] = float(result.get("score", 0))
    except (TypeError, ValueError):
        result["score"] = 0.0
    result.setdefault("criteria", {})
    result.setdefault("issues", [])
    result.setdefault("required_edits", [])
    result.setdefault("praise", [])
    result.setdefault("reasoning", "")
    # Verdict is a *decision*: derive it from the score threshold so it is consistent and auditable,
    # and never accept a draft over the hard character limit.
    from app.platforms import get_platform

    over_limit = facts["chars"] > get_platform(platform).max_chars
    if over_limit:
        result["required_edits"] = [f"Cut the draft to <= {get_platform(platform).max_chars} characters."] + list(
            result["required_edits"]
        )
    result["verdict"] = "accept" if (result["score"] >= pass_score and not over_limit) else "revise"
    result["facts"] = facts
    return result
