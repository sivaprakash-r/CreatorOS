from datetime import datetime, timezone

from PIL import Image
import io

from app.services.poster import compose_poster, fallback_background
from app.services.scheduling import DEFAULTS, recommend_slot


def test_fallback_background_size_and_palette():
    img = fallback_background((320, 200), "warm", "seed")
    assert img.size == (320, 200)


def test_compose_poster_without_background_and_with_emoji():
    png = compose_poster(background=None, size=(512, 512), brand="Sunny Side Bakes ☕", headline="Café coffee, at home ☕", subline="5 tiny habits 🎉", palette="warm", seed="x")
    img = Image.open(io.BytesIO(png))
    assert img.size == (512, 512) and img.format == "PNG"


def test_compose_poster_with_background_cover_fit():
    bg = io.BytesIO()
    Image.new("RGB", (300, 100), (10, 200, 10)).save(bg, format="PNG")
    png = compose_poster(background=bg.getvalue(), size=(256, 256), brand="B", headline="Headline that is quite long so it wraps onto lines", subline="", palette="cool")
    assert Image.open(io.BytesIO(png)).size == (256, 256)


class _Piece:
    def __init__(self, platform):
        self.id, self.brand_id, self.platform = "p1", "b1", platform


class _DB:
    def scalars(self, stmt):
        return iter([])


def test_recommend_slot_defaults_when_no_evidence():
    now = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)  # Thursday
    rec = recommend_slot(_DB(), _Piece("linkedin"), now=now)
    assert rec["basis"] == "platform_default" and rec["evidence_posts"] == 0
    assert rec["scheduled_at"] > now
    assert rec["scheduled_at"].hour in DEFAULTS["linkedin"]["hours"]
    assert rec["scheduled_at"].weekday() in DEFAULTS["linkedin"]["weekdays"]
    assert "no performance evidence yet" in rec["reason"]
