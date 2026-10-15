"""Shared prompt-context builders so every agent sees the same brand voice and learnings."""

from __future__ import annotations

import json

from app.platforms import get_platform


def brand_block(profile: dict, stats: dict | None = None) -> str:
    if not profile:
        return "BRAND VOICE PROFILE: (none learned yet — write in a clear, professional voice)"
    lines = ["BRAND VOICE PROFILE (learned from the brand's own past content — follow it closely):"]
    for key in ("summary", "tone", "persona", "sentence_style", "formatting", "emoji_usage"):
        if profile.get(key):
            lines.append(f"- {key}: {profile[key]}")
    for key in ("vocabulary", "signature_moves", "do", "dont"):
        if profile.get(key):
            lines.append(f"- {key}: {', '.join(map(str, profile[key]))}")
    if stats:
        lines.append(
            "- measured style: avg %s chars/post, %s words/sentence, %s emoji/post, %s hashtags/post, "
            "lists in %s%% of posts"
            % (
                stats.get("avg_chars"),
                stats.get("avg_sentence_words"),
                stats.get("emoji_per_post"),
                stats.get("hashtags_per_post"),
                int(100 * stats.get("list_usage_rate", 0)),
            )
        )
    return "\n".join(lines)


def learnings_block(learnings: list[dict], perf_stats: dict | None = None) -> str:
    """Rules distilled from performance feedback. This is what closes the loop."""
    if not learnings and not perf_stats:
        return "PERFORMANCE LEARNINGS: none yet (no performance data has been analysed for this brand)."
    lines = ["PERFORMANCE LEARNINGS (distilled from how this brand's past posts actually performed — apply them):"]
    for lr in learnings:
        lines.append(
            f"- [{lr.get('applies_to', 'general')} | confidence {lr.get('confidence', 0.5):.2f}] "
            f"{lr.get('rule')}  (evidence: {lr.get('insight')})"
        )
    if perf_stats:
        lines.append("Engagement by feature (mean engagement score 0-1, n = posts):")
        for feature, table in perf_stats.items():
            cells = ", ".join(f"{k}={v['mean']:.2f} (n={v['n']})" for k, v in table.items())
            lines.append(f"  * {feature}: {cells}")
    return "\n".join(lines)


def platform_block(platform_key: str) -> str:
    spec = get_platform(platform_key)
    return (
        f"PLATFORM: {spec.label}\nHARD LIMIT: {spec.max_chars} characters. IDEAL: {spec.ideal_min_chars}-"
        f"{spec.ideal_max_chars} characters. MAX HASHTAGS: {spec.max_hashtags}.\nCONVENTIONS: {spec.style}"
    )


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)
