from app.services.features import extract_features, hook_type, length_bucket, style_stats


def test_hook_types():
    assert hook_type("Why do most deploys fail?") == "question"
    assert hook_type("Most teams get Kubernetes wrong.") == "contrarian"
    assert hook_type("We cut spend by 38% in 30 days.") == "statistic"
    assert hook_type("I shipped a feature on Friday and it broke.") == "story"
    assert hook_type("How to run a gateway") == "list"
    assert hook_type("Observability matters.") == "statement"
    assert hook_type("") == "none"


def test_length_buckets():
    assert length_bucket(100) == "short"
    assert length_bucket(500) == "medium"
    assert length_bucket(1200) == "long"
    assert length_bucket(3000) == "very_long"


def test_extract_features_counts():
    text = "Hello there! 🚀\n\n1. one\n2. two\n\nWhat do you think? #ai #ml"
    f = extract_features(text)
    assert f["hashtag_count"] == 2
    assert f["emoji_count"] == 1
    assert f["has_list"] is True
    assert f["has_cta"] is True
    assert f["question_count"] == 1
    assert f["paragraphs"] == 3


def test_style_stats_aggregates():
    stats = style_stats(["Short one. Really.", "Another sample here 🎉 #x", ""])
    assert stats["samples"] == 2
    assert stats["emoji_per_post"] == 0.5
    assert "hook_type_distribution" in stats
    assert style_stats([]) == {}
