"""Seed the two demo brands (learns their voices through Mesh) and generate one starter piece each.

    python scripts/seed.py            # against the local DB in .env
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session_scope  # noqa: E402
from app.mesh import get_mesh_client  # noqa: E402
from app.models import Brand  # noqa: E402
from app.services import brand as brand_service  # noqa: E402
from app.services import studio  # noqa: E402
from app.services.demo import DEMO_BRANDS  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main() -> None:
    init_db()
    mesh = get_mesh_client()
    with session_scope() as db:
        for spec in DEMO_BRANDS:
            if db.scalar(select(Brand).where(Brand.name == spec["name"])):
                print(f"- {spec['name']} already exists")
                continue
            b = brand_service.create_brand(db, name=spec["name"], description=spec["description"])
            brand_service.add_samples(db, b, spec["samples"])
            db.refresh(b)
            brand_service.learn_profile(db, mesh, b)
            print(f"- learned voice for {b.name}: {b.profile.get('summary')}")
            piece = studio.create_piece(db, brand=b, brief="a post about why AI safety is an engineering discipline", platform="linkedin" if "Tech" in b.name else "instagram")
            pid = piece.id
            db.commit()
            p = studio.generate_piece(pid, mesh=mesh)
            print(f"  generated {p.id}: {p.editor_rounds} editor rounds, CQS {p.quality_before} -> {p.quality_after}")


if __name__ == "__main__":
    main()
