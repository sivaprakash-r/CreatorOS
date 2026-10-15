"""Platform specifications: what "good" looks like per platform. Used by the writer, editor,
quality scorer and the adaptation step."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    label: str
    max_chars: int
    ideal_min_chars: int
    ideal_max_chars: int
    max_hashtags: int
    style: str
    image_size: str = "1024x1024"


PLATFORMS: dict[str, PlatformSpec] = {
    "linkedin": PlatformSpec(
        key="linkedin",
        label="LinkedIn",
        max_chars=3000,
        ideal_min_chars=600,
        ideal_max_chars=1500,
        max_hashtags=5,
        style=(
            "Professional but human. Strong first line (it is truncated after ~210 characters, so the hook "
            "must land before 'see more'). Short paragraphs, white space, one idea per line, "
            "optional numbered list, end with a question or clear call to action. 3-5 hashtags at the end."
        ),
        image_size="1024x1024",
    ),
    "x": PlatformSpec(
        key="x",
        label="X / Twitter",
        max_chars=280,
        ideal_min_chars=120,
        ideal_max_chars=270,
        max_hashtags=2,
        style=(
            "One punchy idea in <= 280 characters. No preamble. Specific, quotable, no hashtag spam (max 2). "
            "A thread is NOT wanted — a single post."
        ),
        image_size="1024x1024",
    ),
    "instagram": PlatformSpec(
        key="instagram",
        label="Instagram",
        max_chars=2200,
        ideal_min_chars=300,
        ideal_max_chars=1200,
        max_hashtags=12,
        style=(
            "Caption that supports a visual. First line must hook before the fold (~125 chars). Conversational, "
            "emoji acceptable if on-brand, line breaks between thoughts, CTA to comment/save/share, "
            "8-12 relevant hashtags grouped at the end."
        ),
        image_size="1024x1024",
    ),
    "blog": PlatformSpec(
        key="blog",
        label="Blog / Newsletter",
        max_chars=12000,
        ideal_min_chars=1500,
        ideal_max_chars=5000,
        max_hashtags=0,
        style=(
            "Long-form with a title, a one-paragraph intro that states the thesis, H2 section headings, "
            "concrete examples, and a conclusion with a single recommended action. No hashtags."
        ),
        image_size="1536x1024",
    ),
}


def get_platform(key: str) -> PlatformSpec:
    key = (key or "linkedin").lower().strip()
    aliases = {"twitter": "x", "linked-in": "linkedin", "ig": "instagram", "newsletter": "blog", "medium": "blog"}
    key = aliases.get(key, key)
    if key not in PLATFORMS:
        raise ValueError(f"Unsupported platform '{key}'. Choose one of: {', '.join(PLATFORMS)}")
    return PLATFORMS[key]
