import pytest

from app.agents.learner import feature_stats
from app.platforms import get_platform
from app.services.learning import engagement_score, simulate_metrics
from app.services.quality import cosine, platform_fit_score, score_content, voice_similarity


def test_platform_fit_rewards_good_linkedin_post():
    good = "Most teams get this wrong.\n\n" + ("Concrete sentence with a number 42. " * 25) + "\n\nWhich one do you use?"
    bad = "x" * 4000
    gs, gchecks = platform_fit_score(good, "linkedin")
    bs, bchecks = platform_fit_score(bad, "linkedin")
    assert gs > bs
    assert gchecks["within_hard_limit"] and not bchecks["within_hard_limit"]
    assert gchecks["has_cta"]


def test_platform_fit_x_limit():
    s, checks = platform_fit_score("a" * 281, "x")
    assert checks["within_hard_limit"] is False
    s2, checks2 = platform_fit_score("Short and punchy. What's yours?", "x")
    assert checks2["within_hard_limit"] and s2 > s


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)


def test_voice_similarity_prefers_similar_text(mesh):
    samples = ["kubernetes cluster ownership helm release namespace", "gateway observability tokens budget logs"]
    close = voice_similarity(mesh, "kubernetes helm namespace ownership cluster", samples)
    far = voice_similarity(mesh, "croissant butter bakery pastry sunshine", samples)
    assert close > far
    assert voice_similarity(mesh, "anything", []) == 0.5


def test_score_content_shape(mesh):
    rep = score_content(mesh, "Most teams get it wrong.\n\nHere is a number: 30 days.\n\nWhat do you do?", "linkedin", {}, ["sample one here", "sample two there"])
    assert 0 <= rep.cqs <= 100
    assert set(rep.judge) >= {"hook_strength", "clarity", "specificity"}
    d = rep.as_dict()
    assert "platform_checks" in d and "features" in d


def test_engagement_score_rate_and_absolute():
    assert engagement_score({"impressions": 1000, "likes": 100, "comments": 10, "shares": 5}) == pytest.approx(min(1.0, (100 + 40 + 25) / 1000 / 0.5), abs=1e-3)
    assert engagement_score({"likes": 250}) == pytest.approx(0.5)
    assert engagement_score({}) == 0.0


def test_simulate_metrics_is_deterministic_and_rewards_structure():
    strong = "Most teams get this wrong.\n\n1. Measure it.\n2. Ship it in 30 days.\n\nWhich one do you do?"
    weak = "x " * 1200
    a = simulate_metrics(strong, seed="s")
    b = simulate_metrics(strong, seed="s")
    assert a == b
    assert engagement_score(simulate_metrics(strong, seed="1")) > engagement_score(simulate_metrics(weak, seed="1"))


def test_feature_stats_table():
    items = [
        {"text": "Most teams get it wrong.\n\nWhat do you think?", "engagement": 0.8},
        {"text": "Why does this happen?\n\nTell me.", "engagement": 0.2},
    ]
    stats = feature_stats(items)
    assert stats["hook_type"]["contrarian"]["mean"] == 0.8
    assert stats["hook_type"]["question"]["n"] == 1
    assert "hashtags" in stats and "emoji" in stats


def test_get_platform_aliases_and_errors():
    assert get_platform("twitter").key == "x"
    assert get_platform("LinkedIn").key == "linkedin"
    with pytest.raises(ValueError):
        get_platform("tiktok")
