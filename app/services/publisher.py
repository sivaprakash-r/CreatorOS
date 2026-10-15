"""Publishing adapters.

* simulated — marks the piece published and (optionally) synthesises engagement so the feedback loop
              can run end-to-end without platform credentials.
* x         — real posting to X/Twitter through the v2 API when X_* credentials are configured, plus
              reading public metrics back. Any other platform without credentials falls back to simulated
              and the decision trail says so.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ContentPiece, Decision
from app.services import learning as learning_service

log = logging.getLogger(__name__)


def _compose(piece: ContentPiece) -> str:
    text = piece.final_text.strip()
    if piece.hashtags and piece.platform != "blog":
        tags = " ".join(piece.hashtags)
        if tags not in text:
            text = f"{text}\n\n{tags}"
    return text


def publish(db: Session, piece: ContentPiece) -> ContentPiece:
    settings = get_settings()
    target = piece.publish_target or "simulated"
    now = datetime.now(timezone.utc)
    try:
        if target == "x" and settings.x_api_key:
            external_id, url = _publish_to_x(_compose(piece))
            piece.external_id, piece.external_url = external_id, url
            reasoning = "Posted through the X API v2 with the configured credentials."
        else:
            if target != "simulated":
                reasoning = f"No credentials for '{target}' — published in simulated mode."
            else:
                reasoning = "Simulated publish (no platform credentials configured)."
            target = "simulated"
            piece.external_id = f"sim-{piece.id}"
            piece.external_url = None
        piece.status = "published"
        piece.published_at = now
        piece.publish_target = target
        db.add(
            Decision(
                content_id=piece.id,
                brand_id=piece.brand_id,
                agent="publisher",
                decision_type="published",
                summary=f"Published via {target} at {now.isoformat()}",
                reasoning=reasoning,
                payload={"external_id": piece.external_id, "external_url": piece.external_url},
            )
        )
        db.commit()
        if target == "simulated" and settings.simulate_engagement:
            metrics = learning_service.simulate_metrics(piece.final_text, seed=piece.id)
            learning_service.capture_performance(db, piece, metrics, source="simulated", notes="auto-simulated after publish")
    except Exception as exc:
        log.exception("publish failed for %s", piece.id)
        piece.status = "failed"
        piece.error = str(exc)
        db.commit()
    db.refresh(piece)
    return piece


def _publish_to_x(text: str) -> tuple[str, str]:
    """Post via X API v2 (OAuth 1.0a user context). Requires `requests-oauthlib` at runtime."""
    s = get_settings()
    from requests_oauthlib import OAuth1Session  # type: ignore[import-not-found]

    oauth = OAuth1Session(s.x_api_key, s.x_api_secret, s.x_access_token, s.x_access_secret)
    resp = oauth.post("https://api.twitter.com/2/tweets", json={"text": text[:280]}, timeout=30)
    resp.raise_for_status()
    tweet_id = resp.json()["data"]["id"]
    return tweet_id, f"https://x.com/i/web/status/{tweet_id}"


def fetch_x_metrics(tweet_id: str) -> dict:
    s = get_settings()
    from requests_oauthlib import OAuth1Session  # type: ignore[import-not-found]

    oauth = OAuth1Session(s.x_api_key, s.x_api_secret, s.x_access_token, s.x_access_secret)
    resp = oauth.get(
        f"https://api.twitter.com/2/tweets/{tweet_id}", params={"tweet.fields": "public_metrics"}, timeout=30
    )
    resp.raise_for_status()
    m = resp.json()["data"]["public_metrics"]
    return {
        "impressions": m.get("impression_count", 0),
        "likes": m.get("like_count", 0),
        "comments": m.get("reply_count", 0),
        "shares": m.get("retweet_count", 0) + m.get("quote_count", 0),
        "saves": m.get("bookmark_count", 0),
        "clicks": 0,
    }
