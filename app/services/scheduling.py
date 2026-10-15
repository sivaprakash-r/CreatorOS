"""Best-slot recommendation for the scheduler.

Evidence-first: when the brand has enough published pieces with performance on the platform, the
hour-of-day (UTC) with the highest mean engagement wins. Otherwise fall back to platform defaults.
The reason is returned so the decision trail can record why the slot was chosen.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentPiece

# default publishing windows, hours in UTC, weekday preference
DEFAULTS: dict[str, dict] = {
    "linkedin": {"hours": [3, 8, 12], "weekdays": [1, 2, 3], "why": "LinkedIn engagement peaks on Tue–Thu mornings in the audience's workday (08:30 IST / 09:00 CET / 08:00 ET windows)"},
    "x": {"hours": [7, 12, 16], "weekdays": [0, 1, 2, 3, 4], "why": "X traffic is highest mid-morning to late afternoon on weekdays"},
    "instagram": {"hours": [6, 13, 15], "weekdays": [0, 1, 2, 3, 4, 5, 6], "why": "Instagram sees lunch-hour and early-evening peaks every day"},
    "blog": {"hours": [7], "weekdays": [1, 2], "why": "Long-form reads best when it lands early on Tue/Wed and can be shared across the week"},
}
MIN_EVIDENCE = 3


def recommend_slot(db: Session, piece: ContentPiece, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    spec = DEFAULTS.get(piece.platform, DEFAULTS["linkedin"])
    earliest = now + timedelta(minutes=10)

    # evidence from this brand's published pieces on this platform
    by_hour: dict[int, list[float]] = defaultdict(list)
    rows = db.scalars(
        select(ContentPiece).where(
            ContentPiece.brand_id == piece.brand_id, ContentPiece.platform == piece.platform,
            ContentPiece.status == "published", ContentPiece.id != piece.id,
        )
    )
    n = 0
    for p in rows:
        if p.performance and p.published_at:
            by_hour[p.published_at.astimezone(timezone.utc).hour].append(p.performance[-1].engagement_score)
            n += 1
    if n >= MIN_EVIDENCE and by_hour:
        best_hour, scores = max(by_hour.items(), key=lambda kv: mean(kv[1]))
        hours = [best_hour]
        weekdays = spec["weekdays"]
        basis = "performance"
        why = (f"{n} published {piece.platform} posts analysed: posts published around {best_hour:02d}:00 UTC averaged "
               f"{mean(scores):.2f} engagement (n={len(scores)}), the best hour so far")
    else:
        hours, weekdays, basis = spec["hours"], spec["weekdays"], "platform_default"
        why = spec["why"] + f" (no performance evidence yet: {n}/{MIN_EVIDENCE} published posts with metrics)"

    # next slot >= earliest matching hour + weekday
    candidate = earliest.replace(minute=0, second=0, microsecond=0)
    for _ in range(24 * 14):
        if candidate >= earliest and candidate.hour in hours and candidate.weekday() in weekdays:
            break
        candidate += timedelta(hours=1)
    return {"scheduled_at": candidate, "reason": why, "basis": basis, "evidence_posts": n}
