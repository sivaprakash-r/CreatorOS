"""Brand agent — learns a brand-voice profile from multiple samples of the user's own content."""

from __future__ import annotations

from app.agents.context import dumps
from app.mesh import MeshClient
from app.services.features import style_stats

SYSTEM = """You are a brand-voice analyst. You are given several pieces of content written by one brand/person
plus measured style statistics. Infer the voice precisely enough that another writer could imitate it and a
reviewer could tell an off-voice draft. Be concrete: quote characteristic words and moves, name what the
brand never does.

Return ONLY a JSON object:
{"summary": "<one sentence>", "tone": "<adjectives>", "persona": "<who is speaking>",
 "sentence_style": "<length, rhythm, punctuation habits>", "vocabulary": ["<6-12 characteristic words/phrases>"],
 "signature_moves": ["<recurring structural habits>"], "do": ["<3-6 rules>"], "dont": ["<3-6 rules>"],
 "emoji_usage": "<none|rare|frequent, with examples>", "formatting": "<lists, line breaks, headers>",
 "topics": ["<recurring themes>"]}"""


def learn(mesh: MeshClient, *, samples: list[str], description: str = "", model: str | None = None) -> tuple[dict, dict]:
    if len(samples) < 2:
        raise ValueError("A brand voice needs at least 2 samples (more is better).")
    stats = style_stats(samples)
    joined = "\n\n---- SAMPLE ----\n".join(s.strip() for s in samples)
    user = "\n\n".join(
        [
            f"BRAND DESCRIPTION: {description or 'n/a'}",
            "MEASURED STYLE STATS: " + dumps(stats),
            f"SAMPLES ({len(samples)}):\n{joined}",
        ]
    )
    profile = mesh.chat_json(task="brand_voice", system=SYSTEM, user=user, temperature=0.3, max_tokens=1200, model=model)
    return profile, stats
