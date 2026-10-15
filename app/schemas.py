"""Pydantic request / response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SampleIn(BaseModel):
    text: str = Field(min_length=20)
    platform: str = "linkedin"


class BrandCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    samples: list[SampleIn] = Field(default_factory=list, description="Past content to learn the voice from (>= 2)")


class SamplesAdd(BaseModel):
    samples: list[SampleIn] = Field(min_length=1)
    relearn: bool = True


class BrandOut(BaseModel):
    id: str
    name: str
    description: str
    profile: dict
    profile_stats: dict
    sample_count: int
    created_at: datetime
    example_brief: str | None = None
    example_platforms: list[str] = []


class ContentCreate(BaseModel):
    brand_id: str
    brief: str = Field(min_length=5)
    platforms: list[str] = Field(default_factory=lambda: ["linkedin"], min_length=1)
    scheduled_at: datetime | None = None
    publish_target: str = "simulated"
    generate_image: bool = True
    use_learnings: bool = True


class ScheduleIn(BaseModel):
    scheduled_at: datetime
    publish_target: str = "simulated"
    reason: str = ""  # e.g. the best-slot recommendation that was accepted


class PerformanceIn(BaseModel):
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0
    saves: int = 0
    source: str = "user"
    notes: str = ""


class LearnIn(BaseModel):
    platform: str = "all"


class VersionOut(BaseModel):
    id: str
    version: int
    source: str
    text: str
    hashtags: list
    editor_score: float | None
    critique: dict
    quality_score: float | None
    created_at: datetime


class DecisionOut(BaseModel):
    id: str
    content_id: str | None
    brand_id: str | None
    agent: str
    decision_type: str
    summary: str
    reasoning: str
    payload: dict
    created_at: datetime


class PerformanceOut(BaseModel):
    id: str
    source: str
    impressions: int
    likes: int
    comments: int
    shares: int
    clicks: int
    saves: int
    engagement_score: float
    notes: str
    recorded_at: datetime


class ContentOut(BaseModel):
    id: str
    brand_id: str
    campaign_id: str | None
    brief: str
    platform: str
    status: str
    strategy: dict
    final_text: str
    hashtags: list
    editor_rounds: int
    final_editor_score: float | None
    quality_before: float | None
    quality_after: float | None
    learnings_applied: list
    image_url: str | None
    image_prompt: str | None
    alt_text: str | None
    scheduled_at: datetime | None
    published_at: datetime | None
    publish_target: str
    external_url: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    latest_engagement: float | None = None


class ContentDetail(ContentOut):
    versions: list[VersionOut]
    decisions: list[DecisionOut]
    performance: list[PerformanceOut]


class LearningOut(BaseModel):
    id: str
    platform: str
    applies_to: str
    insight: str
    rule: str
    confidence: float
    evidence: dict
    active: bool
    run_id: str | None
    created_at: datetime


class LearningRunOut(BaseModel):
    id: str
    platform: str
    pieces_analysed: int
    stats: dict
    summary: str
    created_at: datetime
