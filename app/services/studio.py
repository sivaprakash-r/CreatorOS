"""Studio coordinator: turns a brief into a stored, scored, illustrated content piece by running the
LangGraph pipeline and persisting every version and decision as it happens."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import session_scope
from app.graph import build_graph
from app.mesh import MeshClient, get_mesh_client
from app.models import Brand, ContentPiece, ContentVersion, Decision
from app.platforms import get_platform
from app.services import learning as learning_service
from app.services.quality import score_content

log = logging.getLogger(__name__)


class DbSink:
    """Pipeline sink that writes decisions / versions straight to the database (own short sessions,
    so progress is visible in the UI while the graph is still running)."""

    def __init__(self, content_id: str, brand_id: str) -> None:
        self.content_id = content_id
        self.brand_id = brand_id

    def decision(self, *, agent: str, decision_type: str, summary: str, reasoning: str, payload: dict) -> None:
        with session_scope() as db:
            db.add(
                Decision(
                    content_id=self.content_id,
                    brand_id=self.brand_id,
                    agent=agent,
                    decision_type=decision_type,
                    summary=summary,
                    reasoning=reasoning,
                    payload=payload,
                )
            )

    def version(self, *, version: int, source: str, text: str, hashtags: list[str], editor_score: float | None, critique: dict) -> None:
        with session_scope() as db:
            db.add(
                ContentVersion(
                    content_id=self.content_id,
                    version=version,
                    source=source,
                    text=text,
                    hashtags=hashtags,
                    editor_score=editor_score,
                    critique=critique,
                )
            )

    def status(self, status: str) -> None:
        with session_scope() as db:
            piece = db.get(ContentPiece, self.content_id)
            if piece:
                piece.status = status if status == "ready" else f"generating:{status}"


def create_piece(db: Session, *, brand: Brand, brief: str, platform: str, campaign_id: str | None = None) -> ContentPiece:
    get_platform(platform)  # validates
    piece = ContentPiece(brand_id=brand.id, brief=brief.strip(), platform=get_platform(platform).key, campaign_id=campaign_id)
    db.add(piece)
    db.commit()
    db.refresh(piece)
    return piece


def generate_piece(
    content_id: str,
    *,
    mesh: MeshClient | None = None,
    settings: Settings | None = None,
    use_learnings: bool = True,
    generate_image: bool = True,
    score: bool = True,
) -> ContentPiece:
    """Run the full pipeline for an existing ContentPiece. Safe to call from a background task."""
    settings = settings or get_settings()
    mesh = mesh or get_mesh_client()

    with session_scope() as db:
        piece = db.get(ContentPiece, content_id)
        if piece is None:
            raise ValueError(f"content {content_id} not found")
        brand = db.get(Brand, piece.brand_id)
        learnings = learning_service.active_learnings(db, brand.id, piece.platform) if use_learnings else []
        perf_stats = learning_service.latest_perf_stats(db, brand.id, piece.platform) if use_learnings else None
        state = {
            "content_id": piece.id,
            "brief": piece.brief,
            "platform": piece.platform,
            "brand_profile": brand.profile or {},
            "brand_stats": brand.profile_stats or {},
            "learnings": learnings,
            "perf_stats": perf_stats,
            "generate_image": generate_image,
            "brand_name": brand.name,
            "trace": [],
        }
        brand_profile = brand.profile or {}
        brand_samples = [s.text for s in brand.samples]
        platform = piece.platform
        brand_id = brand.id

    sink = DbSink(content_id, brand_id)
    graph = build_graph(mesh, settings, sink, settings.images_dir)
    try:
        final = graph.invoke(state)
    except Exception as exc:
        log.exception("pipeline failed for %s", content_id)
        with session_scope() as db:
            p = db.get(ContentPiece, content_id)
            p.status = "failed"
            p.error = str(exc)
        raise

    quality_before = quality_after = None
    if score:
        try:
            qb = score_content(mesh, final["first_draft"], platform, brand_profile, brand_samples)
            qa = score_content(mesh, final["final_text"], platform, brand_profile, brand_samples)
            quality_before, quality_after = qb.cqs, qa.cqs
            sink.decision(
                agent="evaluator",
                decision_type="quality_scored",
                summary=f"CQS before editor loop {qb.cqs} → after {qa.cqs} ({qa.cqs - qb.cqs:+.1f})",
                reasoning="Content Quality Score = 25·platform_fit + 25·voice_similarity + 50·LLM-judge; "
                "scored on the first draft and on the final draft.",
                payload={"before": qb.as_dict(), "after": qa.as_dict()},
            )
        except Exception as exc:  # scoring must never block delivery
            log.warning("quality scoring failed: %s", exc)

    with session_scope() as db:
        p = db.get(ContentPiece, content_id)
        p.strategy = {k: v for k, v in final["strategy"].items() if not k.startswith("_")}
        p.final_text = final["final_text"]
        p.hashtags = final.get("hashtags", [])
        p.editor_rounds = final.get("round", 0)
        p.final_editor_score = final.get("editor_score")
        p.image_prompt = final.get("image_prompt")
        p.alt_text = final.get("alt_text")
        p.image_path = final.get("image_path")
        p.learnings_applied = [lr["id"] for lr in state["learnings"]]
        p.quality_before = quality_before
        p.quality_after = quality_after
        p.status = "ready"
        p.error = None
        for v in p.versions:
            if v.version == 1 and quality_before is not None:
                v.quality_score = quality_before
            if v.version == p.versions[-1].version and quality_after is not None:
                v.quality_score = quality_after
        db.flush()
        db.refresh(p)
        _ = (p.versions, p.decisions, p.performance)  # eager-load for use after the session closes
        return p


def schedule_piece(db: Session, piece: ContentPiece, when: datetime, target: str = "simulated", reason: str = "") -> ContentPiece:
    if piece.status not in ("ready", "scheduled", "failed"):
        raise ValueError(f"Cannot schedule a piece in status '{piece.status}'")
    piece.scheduled_at = when
    piece.publish_target = target
    piece.status = "scheduled"
    db.add(
        Decision(
            content_id=piece.id,
            brand_id=piece.brand_id,
            agent="scheduler",
            decision_type="scheduled",
            summary=f"Queued for {when.isoformat()} via {target}",
            reasoning=reason or "User-selected slot; the scheduler publishes when due and then captures engagement.",
            payload={"scheduled_at": when.isoformat(), "target": target},
        )
    )
    db.commit()
    db.refresh(piece)
    return piece
