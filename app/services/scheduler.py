"""APScheduler-driven publishing queue.

A background job polls the database for pieces whose `scheduled_at` is due and publishes them.
Published pieces that went out through a real platform get their metrics refreshed periodically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import ContentPiece
from app.services import learning as learning_service
from app.services import publisher

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def publish_due(now: datetime | None = None) -> int:
    """Publish every scheduled piece whose time has come. Returns the number published."""
    now = now or datetime.now(timezone.utc)
    count = 0
    with session_scope() as db:
        due = list(
            db.scalars(
                select(ContentPiece).where(ContentPiece.status == "scheduled", ContentPiece.scheduled_at <= now)
            )
        )
        for piece in due:
            publisher.publish(db, piece)
            count += 1
    if count:
        log.info("published %d due piece(s)", count)
    return count


def refresh_real_metrics() -> int:
    """Pull public metrics for pieces published through a real platform API."""
    settings = get_settings()
    if not settings.x_api_key:
        return 0
    updated = 0
    with session_scope() as db:
        for piece in db.scalars(select(ContentPiece).where(ContentPiece.status == "published", ContentPiece.publish_target == "x")):
            if not piece.external_id:
                continue
            try:
                metrics = publisher.fetch_x_metrics(piece.external_id)
                learning_service.capture_performance(db, piece, metrics, source="platform", notes="pulled from X API")
                updated += 1
            except Exception as exc:  # keep going for the others
                log.warning("metric refresh failed for %s: %s", piece.id, exc)
    return updated


def start() -> BackgroundScheduler | None:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled or _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(publish_due, "interval", seconds=settings.scheduler_poll_seconds, id="publish_due", max_instances=1)
    _scheduler.add_job(refresh_real_metrics, "interval", minutes=30, id="refresh_metrics", max_instances=1)
    _scheduler.start()
    log.info("scheduler started (poll every %ss)", settings.scheduler_poll_seconds)
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
