"""Brand-voice service: create brands, add samples, (re)learn the profile."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import brand as brand_agent
from app.mesh import MeshClient
from app.models import Brand, BrandSample, Decision


def create_brand(db: Session, *, name: str, description: str = "") -> Brand:
    brand = Brand(name=name.strip(), description=description.strip())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def add_samples(db: Session, brand: Brand, samples: list[dict]) -> list[BrandSample]:
    rows = [BrandSample(brand_id=brand.id, text=s["text"].strip(), platform=s.get("platform", "linkedin")) for s in samples if s.get("text", "").strip()]
    db.add_all(rows)
    db.commit()
    return rows


def learn_profile(db: Session, mesh: MeshClient, brand: Brand) -> Brand:
    samples = [s.text for s in brand.samples]
    profile, stats = brand_agent.learn(mesh, samples=samples, description=brand.description)
    brand.profile = profile
    brand.profile_stats = stats
    db.add(
        Decision(
            brand_id=brand.id,
            agent="brand",
            decision_type="voice_profile_learned",
            summary=f"Learned voice profile from {len(samples)} samples: {profile.get('summary', '')}",
            reasoning="Profile = LLM analysis of the samples + measured style statistics; it is injected into every "
            "strategist / writer / editor prompt for this brand.",
            payload={"profile": profile, "stats": stats},
        )
    )
    db.commit()
    db.refresh(brand)
    return brand


def get_brand(db: Session, brand_id: str) -> Brand | None:
    return db.get(Brand, brand_id)


def list_brands(db: Session) -> list[Brand]:
    return list(db.scalars(select(Brand).order_by(Brand.created_at)))
