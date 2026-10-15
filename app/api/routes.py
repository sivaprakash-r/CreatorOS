"""REST API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.db import get_db
from app.mesh import get_mesh_client
from app.models import Brand, ContentPiece, Decision, Learning, LearningRun
from app.platforms import PLATFORMS, get_platform
from app.services import brand as brand_service
from app.services import learning as learning_service
from app.services import publisher, scheduler, scheduling
from app.services import studio
from app.services.demo import DEMO_BRANDS

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ helpers
def _brand_out(b: Brand) -> schemas.BrandOut:
    demo = next((d for d in DEMO_BRANDS if d["name"] == b.name), None)
    return schemas.BrandOut(
        id=b.id, name=b.name, description=b.description, profile=b.profile or {}, profile_stats=b.profile_stats or {},
        sample_count=len(b.samples), created_at=b.created_at,
        example_brief=demo["example_brief"] if demo else None,
        example_platforms=demo["example_platforms"] if demo else [],
    )


def _content_out(p: ContentPiece) -> dict:
    return {
        "id": p.id, "brand_id": p.brand_id, "campaign_id": p.campaign_id, "brief": p.brief, "platform": p.platform,
        "status": p.status, "strategy": p.strategy or {}, "final_text": p.final_text, "hashtags": p.hashtags or [],
        "editor_rounds": p.editor_rounds, "final_editor_score": p.final_editor_score,
        "quality_before": p.quality_before, "quality_after": p.quality_after,
        "learnings_applied": p.learnings_applied or [],
        "image_url": f"/api/content/{p.id}/image" if p.image_path else None,
        "image_prompt": p.image_prompt, "alt_text": p.alt_text,
        "scheduled_at": p.scheduled_at, "published_at": p.published_at, "publish_target": p.publish_target,
        "external_url": p.external_url, "error": p.error, "created_at": p.created_at, "updated_at": p.updated_at,
        "latest_engagement": learning_service.latest_engagement(p),
    }


def _get_brand(db: Session, brand_id: str) -> Brand:
    b = db.get(Brand, brand_id)
    if not b:
        raise HTTPException(404, "brand not found")
    return b


def _get_piece(db: Session, content_id: str) -> ContentPiece:
    p = db.get(ContentPiece, content_id)
    if not p:
        raise HTTPException(404, "content not found")
    return p


# ------------------------------------------------------------------- system
@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "mesh_base_url": s.mesh_base_url,
        "mesh_mock": s.mesh_mock,
        "chat_model": s.mesh_chat_model,
        "image_model": s.mesh_image_model,
        "scheduler": s.scheduler_enabled,
    }


@router.get("/platforms")
def platforms():
    return [
        {"key": p.key, "label": p.label, "max_chars": p.max_chars, "max_hashtags": p.max_hashtags, "style": p.style}
        for p in PLATFORMS.values()
    ]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    pieces = list(db.scalars(select(ContentPiece)))
    scored = [p for p in pieces if p.quality_before is not None and p.quality_after is not None]
    improved = [p for p in scored if p.quality_after > p.quality_before]
    return {
        "brands": db.scalar(select(func.count(Brand.id))) or 0,
        "pieces": len(pieces),
        "published": len([p for p in pieces if p.status == "published"]),
        "scheduled": len([p for p in pieces if p.status == "scheduled"]),
        "with_performance": len([p for p in pieces if p.performance]),
        "active_learnings": db.scalar(select(func.count(Learning.id)).where(Learning.active == True)) or 0,  # noqa: E712
        "decisions": db.scalar(select(func.count(Decision.id))) or 0,
        "avg_quality_before": round(sum(p.quality_before for p in scored) / len(scored), 1) if scored else None,
        "avg_quality_after": round(sum(p.quality_after for p in scored) / len(scored), 1) if scored else None,
        "editor_improved_share": round(len(improved) / len(scored), 2) if scored else None,
        "avg_editor_rounds": round(sum(p.editor_rounds for p in pieces) / len(pieces), 2) if pieces else None,
    }


# ------------------------------------------------------------------- brands
@router.get("/brands", response_model=list[schemas.BrandOut])
def list_brands(db: Session = Depends(get_db)):
    return [_brand_out(b) for b in brand_service.list_brands(db)]


@router.post("/brands", response_model=schemas.BrandOut, status_code=201)
def create_brand(body: schemas.BrandCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Brand).where(Brand.name == body.name.strip())):
        raise HTTPException(409, "a brand with that name already exists")
    brand = brand_service.create_brand(db, name=body.name, description=body.description)
    if body.samples:
        brand_service.add_samples(db, brand, [s.model_dump() for s in body.samples])
        db.refresh(brand)
        if len(brand.samples) >= 2:
            brand_service.learn_profile(db, get_mesh_client(), brand)
    return _brand_out(brand)


@router.get("/brands/{brand_id}", response_model=schemas.BrandOut)
def get_brand(brand_id: str, db: Session = Depends(get_db)):
    return _brand_out(_get_brand(db, brand_id))


@router.get("/brands/{brand_id}/samples")
def brand_samples(brand_id: str, db: Session = Depends(get_db)):
    b = _get_brand(db, brand_id)
    return [{"id": s.id, "text": s.text, "platform": s.platform, "created_at": s.created_at} for s in b.samples]


@router.post("/brands/{brand_id}/samples", response_model=schemas.BrandOut)
def add_samples(brand_id: str, body: schemas.SamplesAdd, db: Session = Depends(get_db)):
    b = _get_brand(db, brand_id)
    brand_service.add_samples(db, b, [s.model_dump() for s in body.samples])
    db.refresh(b)
    if body.relearn and len(b.samples) >= 2:
        brand_service.learn_profile(db, get_mesh_client(), b)
    return _brand_out(b)


@router.post("/brands/{brand_id}/learn-voice", response_model=schemas.BrandOut)
def learn_voice(brand_id: str, db: Session = Depends(get_db)):
    b = _get_brand(db, brand_id)
    if len(b.samples) < 2:
        raise HTTPException(400, "add at least 2 samples first")
    return _brand_out(brand_service.learn_profile(db, get_mesh_client(), b))


# ------------------------------------------------------------------ content
@router.post("/content", response_model=list[schemas.ContentOut], status_code=201)
def create_content(
    body: schemas.ContentCreate,
    background: BackgroundTasks,
    wait: bool = Query(False, description="Run the pipeline synchronously (tests / scripts)"),
    db: Session = Depends(get_db),
):
    brand = _get_brand(db, body.brand_id)
    try:
        platforms = [get_platform(p).key for p in body.platforms]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    campaign_id = uuid.uuid4().hex[:12] if len(platforms) > 1 else None
    pieces = [studio.create_piece(db, brand=brand, brief=body.brief, platform=p, campaign_id=campaign_id) for p in platforms]
    for p in pieces:
        if body.scheduled_at:
            p.scheduled_at = body.scheduled_at
            p.publish_target = body.publish_target
    db.commit()

    def _run(content_id: str) -> None:
        try:
            studio.generate_piece(content_id, use_learnings=body.use_learnings, generate_image=body.generate_image)
            if body.scheduled_at:
                from app.db import session_scope

                with session_scope() as s:
                    piece = s.get(ContentPiece, content_id)
                    studio.schedule_piece(s, piece, body.scheduled_at, body.publish_target)
        except Exception:  # error already recorded on the piece
            pass

    if wait:
        for p in pieces:
            _run(p.id)
        db.expire_all()  # the pipeline wrote through its own sessions
        return [_content_out(_get_piece(db, p.id)) for p in pieces]
    for p in pieces:
        background.add_task(_run, p.id)
    return [_content_out(p) for p in pieces]


@router.get("/content", response_model=list[schemas.ContentOut])
def list_content(brand_id: str | None = None, status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(ContentPiece).order_by(ContentPiece.created_at.desc()).limit(limit)
    if brand_id:
        stmt = stmt.where(ContentPiece.brand_id == brand_id)
    if status:
        stmt = stmt.where(ContentPiece.status == status)
    return [_content_out(p) for p in db.scalars(stmt)]


@router.get("/content/{content_id}", response_model=schemas.ContentDetail)
def get_content(content_id: str, db: Session = Depends(get_db)):
    p = _get_piece(db, content_id)
    out = _content_out(p)
    out["versions"] = [
        {"id": v.id, "version": v.version, "source": v.source, "text": v.text, "hashtags": v.hashtags or [],
         "editor_score": v.editor_score, "critique": v.critique or {}, "quality_score": v.quality_score, "created_at": v.created_at}
        for v in p.versions
    ]
    out["decisions"] = [_decision_out(d) for d in p.decisions]
    out["performance"] = [
        {"id": x.id, "source": x.source, "impressions": x.impressions, "likes": x.likes, "comments": x.comments,
         "shares": x.shares, "clicks": x.clicks, "saves": x.saves, "engagement_score": x.engagement_score,
         "notes": x.notes, "recorded_at": x.recorded_at}
        for x in p.performance
    ]
    return out


@router.get("/content/{content_id}/image")
def get_image(content_id: str, db: Session = Depends(get_db)):
    p = _get_piece(db, content_id)
    if not p.image_path or not Path(p.image_path).exists():
        raise HTTPException(404, "no image for this piece")
    return FileResponse(p.image_path, media_type="image/png")


@router.get("/content/{content_id}/best-slot")
def best_slot(content_id: str, db: Session = Depends(get_db)):
    """Recommended publish time with the evidence behind it (performance by hour, or platform defaults)."""
    return scheduling.recommend_slot(db, _get_piece(db, content_id))


@router.post("/content/{content_id}/schedule", response_model=schemas.ContentOut)
def schedule_content(content_id: str, body: schemas.ScheduleIn, db: Session = Depends(get_db)):
    p = _get_piece(db, content_id)
    when = body.scheduled_at if body.scheduled_at.tzinfo else body.scheduled_at.replace(tzinfo=timezone.utc)
    try:
        return _content_out(studio.schedule_piece(db, p, when, body.publish_target, reason=body.reason))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/content/{content_id}/publish", response_model=schemas.ContentOut)
def publish_now(content_id: str, db: Session = Depends(get_db)):
    p = _get_piece(db, content_id)
    if p.status not in ("ready", "scheduled", "failed"):
        raise HTTPException(400, f"cannot publish a piece in status '{p.status}'")
    return _content_out(publisher.publish(db, p))


@router.post("/content/{content_id}/performance", response_model=schemas.ContentOut)
def add_performance(content_id: str, body: schemas.PerformanceIn, db: Session = Depends(get_db)):
    p = _get_piece(db, content_id)
    if p.status != "published":
        raise HTTPException(400, "performance can only be recorded for published content")
    learning_service.capture_performance(db, p, body.model_dump(), source=body.source, notes=body.notes)
    db.refresh(p)
    return _content_out(p)


@router.post("/content/{content_id}/regenerate", response_model=schemas.ContentOut)
def regenerate(content_id: str, background: BackgroundTasks, wait: bool = False, db: Session = Depends(get_db)):
    """Re-run the pipeline for the same brief (e.g. after a learning cycle) as a NEW piece."""
    src = _get_piece(db, content_id)
    brand = _get_brand(db, src.brand_id)
    new = studio.create_piece(db, brand=brand, brief=src.brief, platform=src.platform, campaign_id=src.campaign_id)
    if wait:
        studio.generate_piece(new.id)
        db.expire_all()
        return _content_out(_get_piece(db, new.id))
    background.add_task(studio.generate_piece, new.id)
    return _content_out(new)


# ----------------------------------------------------------------- learning
@router.post("/brands/{brand_id}/learn", response_model=schemas.LearningRunOut)
def learn(brand_id: str, body: schemas.LearnIn, db: Session = Depends(get_db)):
    b = _get_brand(db, brand_id)
    try:
        run = learning_service.run_learning(db, get_mesh_client(), b, platform=body.platform)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return _run_out(run)


@router.get("/brands/{brand_id}/learnings", response_model=list[schemas.LearningOut])
def learnings(brand_id: str, include_inactive: bool = False, db: Session = Depends(get_db)):
    _get_brand(db, brand_id)
    stmt = select(Learning).where(Learning.brand_id == brand_id).order_by(Learning.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(Learning.active == True)  # noqa: E712
    return [
        {"id": l.id, "platform": l.platform, "applies_to": l.applies_to, "insight": l.insight, "rule": l.rule,
         "confidence": l.confidence, "evidence": l.evidence or {}, "active": l.active, "run_id": l.run_id, "created_at": l.created_at}
        for l in db.scalars(stmt)
    ]


def _run_out(r: LearningRun) -> dict:
    return {"id": r.id, "platform": r.platform, "pieces_analysed": r.pieces_analysed, "stats": r.stats or {}, "summary": r.summary, "created_at": r.created_at}


@router.get("/brands/{brand_id}/learning-runs", response_model=list[schemas.LearningRunOut])
def learning_runs(brand_id: str, db: Session = Depends(get_db)):
    _get_brand(db, brand_id)
    return [_run_out(r) for r in db.scalars(select(LearningRun).where(LearningRun.brand_id == brand_id).order_by(LearningRun.created_at.desc()))]


# ---------------------------------------------------------------- decisions
def _decision_out(d: Decision) -> dict:
    return {"id": d.id, "content_id": d.content_id, "brand_id": d.brand_id, "agent": d.agent, "decision_type": d.decision_type,
            "summary": d.summary, "reasoning": d.reasoning, "payload": d.payload or {}, "created_at": d.created_at}


@router.get("/decisions", response_model=list[schemas.DecisionOut])
def decisions(brand_id: str | None = None, content_id: str | None = None, agent: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    stmt = select(Decision).order_by(Decision.created_at.desc()).limit(limit)
    if brand_id:
        stmt = stmt.where(Decision.brand_id == brand_id)
    if content_id:
        stmt = stmt.where(Decision.content_id == content_id)
    if agent:
        stmt = stmt.where(Decision.agent == agent)
    return [_decision_out(d) for d in db.scalars(stmt)]


# ---------------------------------------------------------------- scheduler
@router.post("/scheduler/run")
def scheduler_run():
    """Publish everything that is due right now (the background job does this automatically)."""
    return {"published": scheduler.publish_due(datetime.now(timezone.utc))}


# --------------------------------------------------------------------- demo
@router.post("/demo/seed")
def demo_seed(db: Session = Depends(get_db)):
    """Create the two demo brands (with samples + learned voice) if they don't exist yet."""
    created = []
    for spec in DEMO_BRANDS:
        if db.scalar(select(Brand).where(Brand.name == spec["name"])):
            continue
        b = brand_service.create_brand(db, name=spec["name"], description=spec["description"])
        brand_service.add_samples(db, b, spec["samples"])
        db.refresh(b)
        brand_service.learn_profile(db, get_mesh_client(), b)
        created.append(_brand_out(b))
    return {"created": created, "brands": [_brand_out(b) for b in brand_service.list_brands(db)]}
