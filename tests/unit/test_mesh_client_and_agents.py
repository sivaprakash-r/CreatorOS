import pytest

from app.agents import editor, strategist, writer
from app.mesh.client import MeshClient, parse_json_object


def test_parse_json_object_tolerates_fences_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_object("no json here")


def test_client_requires_key_unless_mock():
    with pytest.raises(RuntimeError):
        MeshClient(api_key="", mock=False)
    c = MeshClient(api_key="rsk_test", mock=False)
    assert c._client is not None and "meshapi.ai" in str(c._client.base_url)


def test_mock_client_records_calls(mesh):
    out = mesh.chat_json(task="strategist", system="s", user="Brief: AI safety\nPlatform: linkedin")
    assert out["hook"] and out["reasoning"]
    assert mesh.calls[-1].task == "strategist" and mesh.calls[-1].mock
    assert len(mesh.embed(["a", "b"])) == 2
    assert mesh.generate_image("x").startswith(b"\x89PNG")


def test_editor_verdict_follows_threshold_and_hard_limit(mesh):
    crit = editor.critique(mesh, platform="x", draft="a" * 300, strategy={}, brand_profile={}, learnings=[], round_no=1, pass_score=7.5)
    assert crit["verdict"] == "revise"  # over the X hard limit, regardless of score
    assert any("Cut the draft" in e for e in crit["required_edits"])
    crit2 = editor.critique(mesh, platform="x", draft="fine", strategy={}, brand_profile={}, learnings=[], round_no=2, pass_score=7.5)
    assert crit2["verdict"] == "accept"  # mock editor accepts on the second round
    assert crit2["score"] >= 7.5


def test_strategist_and_writer_prompts_contain_learnings(mesh, monkeypatch):
    captured = {}

    def fake_chat(**kw):
        captured[kw["task"]] = kw["user"]
        return MeshClient._mock_chat(mesh, kw["task"], kw["system"], kw["user"], True)

    monkeypatch.setattr(mesh, "chat", fake_chat)
    learnings = [{"id": "L1", "rule": "Open with a contrarian claim.", "insight": "contrarian hooks won", "confidence": 0.7, "applies_to": "hook"}]
    strat = strategist.run(mesh, brief="AI safety", platform="linkedin", brand_profile={"summary": "direct"}, brand_stats={}, learnings=learnings, perf_stats={"hook_type": {"contrarian": {"mean": 0.8, "n": 3}}})
    assert "Open with a contrarian claim." in captured["strategist"]
    assert "contrarian=0.80 (n=3)" in captured["strategist"]
    assert "direct" in captured["strategist"]
    d = writer.draft(mesh, brief="AI safety", platform="linkedin", strategy=strat, brand_profile={"summary": "direct"}, brand_stats={}, learnings=learnings)
    assert "Open with a contrarian claim." in captured["writer"]
    assert d["draft"] and all(h.startswith("#") for h in d["hashtags"])
