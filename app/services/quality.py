"""Content Quality Score (CQS) — the quality measure used for self-evaluation.

CQS ∈ [0, 100] = 25 · platform_fit + 25 · voice_similarity + 50 · judge_score

* platform_fit     — deterministic rule checks against the platform spec (length window, hook before
                     the fold, hashtag budget, CTA presence, no URL spam).
* voice_similarity — cosine similarity between the piece and the centroid of the brand's sample
                     embeddings (embeddings via Mesh), rescaled so that typical values spread 0..1.
* judge_score      — an LLM judge (via Mesh) scoring six criteria 1-10, averaged, with a prompt that
                     is *different* from the editor's prompt so the editor is not grading itself.

The same function scores first drafts and post-editor drafts, and pieces generated with and
without learnings, which is what `scripts/evaluate.py` reports.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from app.mesh import MeshClient
from app.platforms import get_platform
from app.services.features import extract_features, first_line

JUDGE_CRITERIA = ["hook_strength", "clarity", "specificity", "brand_voice_fit", "platform_fit", "cta_quality"]

JUDGE_SYSTEM = """You are an impartial content quality judge. You score social/blog content on six criteria
from 1 (poor) to 10 (excellent). Be strict and consistent: a 10 is rare. Return ONLY a JSON object:
{"hook_strength": n, "clarity": n, "specificity": n, "brand_voice_fit": n, "platform_fit": n,
 "cta_quality": n, "reasoning": "<one or two sentences>"}
Criteria:
- hook_strength: does the first line stop the scroll and promise value?
- clarity: is it easy to follow; one idea per paragraph; no filler?
- specificity: concrete examples, numbers, named trade-offs instead of generic advice?
- brand_voice_fit: matches the given brand voice profile (tone, sentence style, do/don't)?
- platform_fit: respects platform conventions and length described?
- cta_quality: a natural, specific call to action or closing question?"""


@dataclass
class QualityReport:
    cqs: float
    platform_fit: float
    voice_similarity: float
    judge_score: float
    judge: dict
    platform_checks: dict
    features: dict

    def as_dict(self) -> dict:
        return asdict(self)


def platform_fit_score(text: str, platform_key: str) -> tuple[float, dict]:
    spec = get_platform(platform_key)
    f = extract_features(text)
    checks: dict[str, bool] = {}
    checks["within_hard_limit"] = f["chars"] <= spec.max_chars
    checks["in_ideal_length_window"] = spec.ideal_min_chars <= f["chars"] <= spec.ideal_max_chars
    fold = 210 if spec.key == "linkedin" else 125 if spec.key == "instagram" else 280
    checks["hook_before_fold"] = 0 < len(first_line(text)) <= fold
    checks["hashtag_budget"] = f["hashtag_count"] <= spec.max_hashtags
    checks["has_cta"] = f["has_cta"] if spec.key != "blog" else True
    checks["no_url_spam"] = f["url_count"] <= 1
    checks["has_structure"] = f["paragraphs"] >= 2 if spec.key != "x" else True
    weights = {
        "within_hard_limit": 0.25,
        "in_ideal_length_window": 0.15,
        "hook_before_fold": 0.2,
        "hashtag_budget": 0.1,
        "has_cta": 0.15,
        "no_url_spam": 0.05,
        "has_structure": 0.1,
    }
    score = sum(weights[k] for k, ok in checks.items() if ok)
    return round(score, 3), checks


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def voice_similarity(mesh: MeshClient, text: str, samples: list[str]) -> float:
    if not samples:
        return 0.5  # no profile → neutral
    vecs = mesh.embed([text, *samples])
    target, sample_vecs = vecs[0], vecs[1:]
    centroid = [sum(col) / len(sample_vecs) for col in zip(*sample_vecs)]
    sim = cosine(target, centroid)
    # Embedding cosines cluster in a narrow band; rescale 0.3..0.95 → 0..1 so the score is informative.
    return round(min(1.0, max(0.0, (sim - 0.3) / 0.65)), 3)


def judge(mesh: MeshClient, text: str, platform_key: str, brand_profile: dict) -> dict:
    spec = get_platform(platform_key)
    user = (
        f"PLATFORM: {spec.label}\nPLATFORM CONVENTIONS: {spec.style}\n"
        f"BRAND VOICE PROFILE: {brand_profile or 'n/a'}\n\nCONTENT:\n{text}"
    )
    result = mesh.chat_json(task="judge", system=JUDGE_SYSTEM, user=user, temperature=0.0, max_tokens=400)
    scores = {k: float(result.get(k, 5)) for k in JUDGE_CRITERIA}
    scores["reasoning"] = str(result.get("reasoning", ""))
    return scores


def score_content(
    mesh: MeshClient, text: str, platform_key: str, brand_profile: dict, brand_samples: list[str]
) -> QualityReport:
    pf, checks = platform_fit_score(text, platform_key)
    vs = voice_similarity(mesh, text, brand_samples)
    j = judge(mesh, text, platform_key, brand_profile)
    js = sum(j[k] for k in JUDGE_CRITERIA) / (10 * len(JUDGE_CRITERIA))
    cqs = round(100 * (0.25 * pf + 0.25 * vs + 0.5 * js), 1)
    return QualityReport(
        cqs=cqs,
        platform_fit=pf,
        voice_similarity=vs,
        judge_score=round(js, 3),
        judge=j,
        platform_checks=checks,
        features=extract_features(text),
    )
