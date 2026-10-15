"""Visual agent — designs the visual concept for the piece, generates the background through the
Mesh image model and composes a branded poster (brand chip + headline + subline).

Text is composed with Pillow (app/services/poster.py), never asked of the image model, so the
headline always matches the piece. If the image model call fails, a procedural background is used
and the decision trail records the error — a visual is always produced.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.agents.context import brand_block, dumps
from app.mesh import MeshClient
from app.platforms import get_platform
from app.services.poster import PALETTES, compose_poster

log = logging.getLogger(__name__)

SYSTEM = """You are the Visual Director of a content studio. Given a finished piece and the brand voice,
design ONE social visual that matches it. You produce two things:

1. image_prompt — for an image-generation model: the BACKGROUND artwork only. Describe subject, composition,
   style, palette and mood concretely (60-110 words). Absolutely no text, letters, logos, UI or watermarks in
   the image; keep the lower third calm and uncluttered because a headline will be overlaid there.
2. headline + subline — the words that will be typeset ON the image. headline: max 7 words, punchy, drawn from
   the hook or angle (not a copy of the first sentence). subline: max 12 words, the promise or takeaway.

Return ONLY a JSON object:
{"image_prompt": "<...>", "headline": "<...>", "subline": "<...>",
 "palette": "<one of: warm|cool|forest|berry|slate|amber>",
 "style": "<e.g. editorial illustration | flat vector | photo-real | 3D render>",
 "alt_text": "<one sentence accessible description of the finished visual>",
 "reasoning": "<why this concept, palette and headline match the angle and the brand>"}"""


def design(mesh: MeshClient, *, platform: str, text: str, strategy: dict, brand_profile: dict, model: str | None = None) -> dict:
    user = "\n\n".join(
        [
            f"Platform: {platform}",
            brand_block(brand_profile),
            "ANGLE: " + str(strategy.get("angle", "")),
            "HOOK: " + str(strategy.get("hook", "")),
            "PIECE:\n" + text,
        ]
    )
    result = mesh.chat_json(task="visual", system=SYSTEM, user=user, temperature=0.7, max_tokens=600, model=model)
    result.setdefault("image_prompt", f"Abstract editorial illustration about: {strategy.get('angle', text[:80])}, no text")
    result["headline"] = str(result.get("headline") or strategy.get("hook") or text.split("\n")[0])[:80]
    result["subline"] = str(result.get("subline") or strategy.get("cta") or "")[:120]
    if result.get("palette") not in PALETTES:
        result["palette"] = None
    result.setdefault("style", "editorial")
    result.setdefault("alt_text", f"Visual with headline: {result['headline']}")
    result.setdefault("reasoning", "")
    result["_full"] = dumps(result)
    return result


def _size(platform: str) -> tuple[int, int]:
    w, h = get_platform(platform).image_size.split("x")
    return int(w), int(h)


def generate(
    mesh: MeshClient,
    *,
    plan: dict,
    platform: str,
    brand_name: str,
    out_path: Path,
    use_image_model: bool = True,
) -> tuple[Path, dict]:
    """Compose the poster. Returns (path, info) where info says whether the image model was used
    and carries the error text if it failed. Never raises."""
    size = _size(platform)
    background: bytes | None = None
    info: dict = {"image_model_used": False, "error": None, "size": f"{size[0]}x{size[1]}"}
    if use_image_model:
        try:
            background = mesh.generate_image(plan["image_prompt"], size=get_platform(platform).image_size)
            info["image_model_used"] = True
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            log.warning("image model failed, using procedural background: %s", info["error"])
    png = compose_poster(
        background=background,
        size=size,
        brand=brand_name,
        headline=plan["headline"],
        subline=plan.get("subline", ""),
        palette=plan.get("palette"),
        seed=out_path.stem,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png)
    return out_path, info
