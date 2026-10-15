"""ORM models — the data model behind the content loop.

brand ──< brand_samples          (what the voice is learned from)
brand ──< content_pieces ──< content_versions   (every draft / revision)
                          ──< decisions         (auditable decision trail)
                          ──< performance       (engagement, real / user / simulated)
brand ──< learnings               (rules distilled from performance, injected into future generation)
brand ──< learning_runs           (one row per learning cycle, with the statistics it saw)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)  # learned brand-voice profile
    profile_stats: Mapped[dict] = mapped_column(JSON, default=dict)  # measured stats from samples
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    samples: Mapped[list[BrandSample]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    pieces: Mapped[list[ContentPiece]] = relationship(back_populates="brand")
    learnings: Mapped[list[Learning]] = relationship(back_populates="brand", cascade="all, delete-orphan")


class BrandSample(Base):
    __tablename__ = "brand_samples"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32), default="linkedin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    brand: Mapped[Brand] = relationship(back_populates="samples")


class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    brief: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32), default="linkedin")
    status: Mapped[str] = mapped_column(String(24), default="generating", index=True)
    # generating | ready | scheduled | published | failed

    strategy: Mapped[dict] = mapped_column(JSON, default=dict)  # strategist output
    final_text: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    editor_rounds: Mapped[int] = mapped_column(Integer, default=0)
    final_editor_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_before: Mapped[float | None] = mapped_column(Float, nullable=True)  # our quality measure, first draft
    quality_after: Mapped[float | None] = mapped_column(Float, nullable=True)  # after the editor loop
    learnings_applied: Mapped[list] = mapped_column(JSON, default=list)  # learning ids injected into prompts

    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_target: Mapped[str] = mapped_column(String(32), default="simulated")  # simulated | x
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    brand: Mapped[Brand] = relationship(back_populates="pieces")
    versions: Mapped[list[ContentVersion]] = relationship(
        back_populates="piece", cascade="all, delete-orphan", order_by="ContentVersion.version"
    )
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="piece", cascade="all, delete-orphan", order_by="Decision.created_at"
    )
    performance: Mapped[list[Performance]] = relationship(
        back_populates="piece", cascade="all, delete-orphan", order_by="Performance.recorded_at"
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    content_id: Mapped[str] = mapped_column(ForeignKey("content_pieces.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24))  # writer | revision
    text: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    editor_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    critique: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    piece: Mapped[ContentPiece] = relationship(back_populates="versions")


class Decision(Base):
    """One auditable decision made by an agent, linked to the content it belongs to."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    content_id: Mapped[str | None] = mapped_column(ForeignKey("content_pieces.id"), index=True, nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    agent: Mapped[str] = mapped_column(String(32))  # strategist | writer | editor | visual | learner | scheduler ...
    decision_type: Mapped[str] = mapped_column(String(48))
    summary: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    piece: Mapped[ContentPiece | None] = relationship(back_populates="decisions")


class Performance(Base):
    __tablename__ = "performance"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    content_id: Mapped[str] = mapped_column(ForeignKey("content_pieces.id"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="user")  # user | simulated | platform
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)  # normalised 0..1
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    piece: Mapped[ContentPiece] = relationship(back_populates="performance")


class Learning(Base):
    """A rule distilled from performance data. Active learnings are injected into generation prompts."""

    __tablename__ = "learnings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="all")
    applies_to: Mapped[str] = mapped_column(String(32), default="general")  # hook | structure | cta | length | tone ...
    insight: Mapped[str] = mapped_column(Text)
    rule: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)  # {"top": [ids], "bottom": [ids], "stats": {...}}
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    run_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    brand: Mapped[Brand] = relationship(back_populates="learnings")


class LearningRun(Base):
    __tablename__ = "learning_runs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    brand_id: Mapped[str] = mapped_column(String(16), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="all")
    pieces_analysed: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)  # feature → mean engagement table
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
