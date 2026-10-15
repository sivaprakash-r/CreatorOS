"""Performance feedback loop: capture engagement → learn → inject into the next generation.

capture_performance()  stores metrics (real / user-entered / simulated) and computes a normalised
                       engagement score.
run_learning()         analyses every published piece of a brand+platform that has performance data,
                       stores a LearningRun (statistics) and replaces the active Learnings (rules).
active_learnings()     what the strategist / writer / editor receive on the next run.
"""

from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import learner as learner_agent
from app.mesh import MeshClient
from app.models import Brand, ContentPiece, Decision, Learning, LearningRun, Performance
from app.services.features import extract_features

log = logging.getLogger(__name__)

# Weighted engagement: comments/shares/saves are worth more than a like.
WEIGHTS = {"likes": 1.0, "comments": 4.0, "shares": 5.0, "saves": 3.0, "clicks": 2.0}


def engagement_score(m: dict) -> float:
    """Normalised 0..1 score. Rate-based when impressions are known, absolute otherwise."""
    weighted = sum(WEIGHTS[k] * float(m.get(k, 0) or 0) for k in WEIGHTS)
    impressions = float(m.get("impressions", 0) or 0)
    if impressions > 0:
        rate = weighted / impressions  # weighted rate; 0.5 (= excellent) maps to 1.0
        return round(min(1.0, rate / 0.5), 3)
    return round(min(1.0, weighted / 500.0), 3)


def capture_performance(db: Session, piece: ContentPiece, metrics: dict, source: str = "user", notes: str = "") -> Performance:
    perf = Performance(
        content_id=piece.id,
        source=source,
        impressions=int(metrics.get("impressions", 0) or 0),
        likes=int(metrics.get("likes", 0) or 0),
        comments=int(metrics.get("comments", 0) or 0),
        shares=int(metrics.get("shares", 0) or 0),
        clicks=int(metrics.get("clicks", 0) or 0),
        saves=int(metrics.get("saves", 0) or 0),
        engagement_score=engagement_score(metrics),
        notes=notes,
    )
    db.add(perf)
    db.add(
        Decision(
            content_id=piece.id,
            brand_id=piece.brand_id,
            agent="feedback",
            decision_type="performance_captured",
            summary=f"Performance captured ({source}): engagement {perf.engagement_score:.2f} "
            f"(imp={perf.impressions}, likes={perf.likes}, comments={perf.comments}, shares={perf.shares})",
            reasoning="Weighted engagement (comments ×4, shares ×5, saves ×3, clicks ×2, likes ×1) "
            "normalised by impressions.",
            payload={"metrics": metrics, "engagement_score": perf.engagement_score},
        )
    )
    db.commit()
    db.refresh(perf)
    return perf


def simulate_metrics(text: str, seed: str | None = None) -> dict:
    """Synthesise plausible engagement for a published piece (used when no real platform metrics exist).

    The simulator rewards concrete, well-structured posts with a hook and CTA, and penalises walls of
    text — *transparently* (see docs/07-design-decisions.md). It is noisy, so the learner has to
    separate signal from noise exactly as with real data.
    """
    rng = random.Random(seed or text)
    f = extract_features(text)
    base = 0.08
    base += {"contrarian": 0.05, "statistic": 0.04, "story": 0.03, "question": 0.02, "list": 0.02, "statement": 0.0, "none": -0.03}[f["hook_type"]]
    base += 0.03 if f["has_cta"] else -0.02
    base += 0.03 if f["has_numbers"] else 0.0
    base += 0.02 if f["has_list"] else 0.0
    base += {"short": -0.01, "medium": 0.02, "long": 0.01, "very_long": -0.04}[f["length_bucket"]]
    base -= 0.01 * max(0, f["hashtag_count"] - 5)
    base = max(0.01, base + rng.gauss(0, 0.015))
    impressions = int(rng.lognormvariate(7.2, 0.5))  # ~1300 median
    likes = int(impressions * base * rng.uniform(0.5, 0.8))
    comments = int(impressions * base * rng.uniform(0.04, 0.12))
    shares = int(impressions * base * rng.uniform(0.02, 0.08))
    saves = int(impressions * base * rng.uniform(0.02, 0.06))
    clicks = int(impressions * base * rng.uniform(0.05, 0.15))
    return {"impressions": impressions, "likes": likes, "comments": comments, "shares": shares, "saves": saves, "clicks": clicks}


def latest_engagement(piece: ContentPiece) -> float | None:
    if not piece.performance:
        return None
    return piece.performance[-1].engagement_score


def run_learning(db: Session, mesh: MeshClient, brand: Brand, platform: str = "all") -> LearningRun:
    stmt = select(ContentPiece).where(ContentPiece.brand_id == brand.id, ContentPiece.status == "published")
    if platform != "all":
        stmt = stmt.where(ContentPiece.platform == platform)
    pieces = [p for p in db.scalars(stmt) if p.performance]
    items = [{"id": p.id, "text": p.final_text, "engagement": latest_engagement(p)} for p in pieces]
    if len(items) < 2:
        raise ValueError("Need at least 2 published pieces with performance data on this platform to learn.")

    stats, result = learner_agent.analyse(mesh, platform=platform, items=items, brand_profile=brand.profile)
    run = LearningRun(
        brand_id=brand.id,
        platform=platform,
        pieces_analysed=len(items),
        stats=stats,
        summary=result.get("reasoning", ""),
    )
    db.add(run)
    db.flush()

    # Replace previous active learnings for this brand+platform: the newest cycle wins.
    for old in db.scalars(select(Learning).where(Learning.brand_id == brand.id, Learning.platform == platform, Learning.active == True)):  # noqa: E712
        old.active = False

    new_rows: list[Learning] = []
    for ins in result.get("insights", []):
        row = Learning(
            brand_id=brand.id,
            platform=platform,
            applies_to=str(ins.get("applies_to", "general"))[:32],
            insight=str(ins.get("insight", "")),
            rule=str(ins.get("rule", "")),
            confidence=float(ins.get("confidence", 0.5)),
            evidence={**result.get("_evidence", {}), "stop_doing": result.get("stop_doing", [])},
            run_id=run.id,
        )
        db.add(row)
        new_rows.append(row)

    db.add(
        Decision(
            brand_id=brand.id,
            agent="learner",
            decision_type="learning_cycle",
            summary=f"Learned {len(new_rows)} rules from {len(items)} published pieces ({platform}): "
            + " | ".join(r.rule for r in new_rows[:3]),
            reasoning=result.get("reasoning", ""),
            payload={"run_id": run.id, "stats": stats, "stop_doing": result.get("stop_doing", []), "evidence": result.get("_evidence", {})},
        )
    )
    db.commit()
    db.refresh(run)
    return run


def active_learnings(db: Session, brand_id: str, platform: str) -> list[dict]:
    rows = db.scalars(
        select(Learning)
        .where(Learning.brand_id == brand_id, Learning.active == True, Learning.platform.in_([platform, "all"]))  # noqa: E712
        .order_by(Learning.confidence.desc())
    )
    return [
        {"id": r.id, "rule": r.rule, "insight": r.insight, "confidence": r.confidence, "applies_to": r.applies_to, "platform": r.platform}
        for r in rows
    ]


def latest_perf_stats(db: Session, brand_id: str, platform: str) -> dict | None:
    run = db.scalars(
        select(LearningRun)
        .where(LearningRun.brand_id == brand_id, LearningRun.platform.in_([platform, "all"]))
        .order_by(LearningRun.created_at.desc())
    ).first()
    return run.stats if run else None
