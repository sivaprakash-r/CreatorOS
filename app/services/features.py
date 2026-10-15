"""Deterministic text features. Used by the learner (to correlate features with engagement),
by the quality scorer, and by the brand-voice profiler (measured style statistics)."""

from __future__ import annotations

import re
from statistics import mean

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F1E6-\U0001F1FF]"
)
_HASHTAG_RE = re.compile(r"(?<!\w)#\w+")
_URL_RE = re.compile(r"https?://\S+")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def first_line(text: str) -> str:
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def hook_type(text: str) -> str:
    line = first_line(text).lower()
    if not line:
        return "none"
    if line.endswith("?"):
        return "question"
    if re.search(r"\b\d+(%|x|\s*(percent|days|weeks|hours|minutes|months|years|times))\b", line):
        return "statistic"
    if re.search(r"\b(most|everyone|nobody|wrong|stop|myth|unpopular|hot take|contrary|actually)\b", line):
        return "contrarian"
    if re.search(r"\b(i|we|my|our)\b", line) and re.search(r"\b(learned|built|shipped|tried|failed|spent|lost|made)\b", line):
        return "story"
    if re.search(r"\b(how to|\d+ (ways|steps|lessons|things|rules|mistakes))\b", line):
        return "list"
    return "statement"


def length_bucket(n_chars: int) -> str:
    if n_chars < 300:
        return "short"
    if n_chars < 900:
        return "medium"
    if n_chars < 1800:
        return "long"
    return "very_long"


def has_cta(text: str) -> bool:
    tail = " ".join(sentences(text)[-3:]).lower()
    return bool(
        re.search(
            r"\?|\b(comment|share|reply|dm|let me know|what do you|which|try|download|subscribe|follow|save|tell me|drop)\b",
            tail,
        )
    )


def extract_features(text: str) -> dict:
    sents = sentences(text)
    words = re.findall(r"[A-Za-z0-9']+", text)
    n_chars = len(text)
    hashtags = _HASHTAG_RE.findall(text)
    numbered = bool(re.search(r"^\s*(\d+[.)]|[-*•])\s+", text, flags=re.M))
    return {
        "chars": n_chars,
        "words": len(words),
        "sentences": len(sents),
        "avg_sentence_words": round(mean([len(s.split()) for s in sents]), 1) if sents else 0.0,
        "paragraphs": len([p for p in re.split(r"\n\s*\n", text) if p.strip()]),
        "hook_type": hook_type(text),
        "length_bucket": length_bucket(n_chars),
        "has_cta": has_cta(text),
        "has_list": numbered,
        "has_numbers": bool(re.search(r"\d", text)),
        "emoji_count": len(_EMOJI_RE.findall(text)),
        "hashtag_count": len(hashtags),
        "question_count": text.count("?"),
        "exclamation_count": text.count("!"),
        "url_count": len(_URL_RE.findall(text)),
        "first_person": bool(re.search(r"\b(I|we|my|our)\b", text)),
    }


def style_stats(samples: list[str]) -> dict:
    """Aggregate measured style statistics across brand samples."""
    feats = [extract_features(s) for s in samples if s.strip()]
    if not feats:
        return {}

    def avg(key: str) -> float:
        return round(mean(f[key] for f in feats), 2)

    hooks: dict[str, int] = {}
    for f in feats:
        hooks[f["hook_type"]] = hooks.get(f["hook_type"], 0) + 1
    return {
        "samples": len(feats),
        "avg_chars": avg("chars"),
        "avg_sentence_words": avg("avg_sentence_words"),
        "avg_paragraphs": avg("paragraphs"),
        "emoji_per_post": avg("emoji_count"),
        "hashtags_per_post": avg("hashtag_count"),
        "questions_per_post": avg("question_count"),
        "exclamations_per_post": avg("exclamation_count"),
        "list_usage_rate": round(sum(f["has_list"] for f in feats) / len(feats), 2),
        "first_person_rate": round(sum(f["first_person"] for f in feats) / len(feats), 2),
        "hook_type_distribution": hooks,
    }
