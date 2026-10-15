"""The LangGraph pipeline as a unit: the editor loop must actually loop and change the draft."""

from pathlib import Path

from app.config import Settings
from app.graph.pipeline import ListSink, build_graph


def _run(mesh, tmp_path: Path, **overrides):
    settings = Settings(**{"mesh_mock": True, "editor_max_rounds": 2, "editor_pass_score": 7.5, **overrides})
    sink = ListSink()
    graph = build_graph(mesh, settings, sink, tmp_path)
    state = {
        "content_id": "test123",
        "brief": "a LinkedIn post about AI safety",
        "platform": "linkedin",
        "brand_profile": {"summary": "direct"},
        "brand_stats": {},
        "learnings": [],
        "perf_stats": None,
        "generate_image": True,
        "trace": [],
    }
    return graph.invoke(state), sink


def test_editor_loop_changes_the_draft(mesh, tmp_path):
    final, sink = _run(mesh, tmp_path)
    assert final["trace"][:3] == ["strategist", "writer", "editor:1:revise"]
    assert "reviser" in final["trace"]
    assert final["trace"][-2:] == ["visual", "finalize"]
    assert final["first_draft"] != final["final_text"]
    assert len(final["final_text"]) > len(final["first_draft"])
    assert final["round"] == 2 and final["verdict"] == "accept"
    # versions: v1 writer, v2 revision
    assert [v["version"] for v in sink.versions] == [1, 2]
    assert sink.versions[1]["text"] == final["final_text"]
    # the decision trail covers every agent
    agents = [d["agent"] for d in sink.decisions]
    assert agents == ["strategist", "writer", "editor", "writer", "editor", "visual"]
    assert all(d["reasoning"] for d in sink.decisions)
    edits = next(d for d in sink.decisions if d["decision_type"] == "review_round_1")["payload"]["required_edits"]
    assert edits  # the editor asked for concrete edits
    assert (tmp_path / "test123.png").exists()
    assert final["image_prompt"] and final["alt_text"]


def test_graph_structure_has_named_nodes_and_loop(mesh, tmp_path):
    graph = build_graph(mesh, Settings(mesh_mock=True), ListSink(), tmp_path)
    g = graph.get_graph()
    nodes = set(g.nodes)
    assert {"strategist", "writer", "editor", "reviser", "visual", "finalize"} <= nodes
    edges = {(e.source, e.target) for e in g.edges}
    assert ("reviser", "editor") in edges  # the loop back
    assert ("editor", "reviser") in edges and ("editor", "visual") in edges  # conditional branch


def test_max_rounds_cap(mesh, tmp_path):
    # Force the mock editor to always ask for a revision by making the pass score unreachable.
    final, sink = _run(mesh, tmp_path, editor_pass_score=9.9, editor_max_rounds=1)
    assert final["verdict"] == "accept_max_rounds"
    assert final["round"] == 2  # 1 allowed revision round + the final review
