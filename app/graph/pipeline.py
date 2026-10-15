"""LangGraph orchestration — the coordinator that runs the agents and passes work between them.

    strategist ─► writer ─► editor ─┬─(accept, or max rounds)─► visual ─► finalize ─► END
                     ▲              │
                     └── reviser ◄──┘ (verdict == revise)

The editor → reviser → editor cycle is a real loop with a conditional edge; the draft after it is
*different* from the draft before it (verified by tests and by the quality numbers in docs/).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, StateGraph

from app.agents import editor as editor_agent
from app.agents import strategist as strategist_agent
from app.agents import visual as visual_agent
from app.agents import writer as writer_agent
from app.config import Settings
from app.mesh import MeshClient


class ContentState(TypedDict, total=False):
    # inputs
    content_id: str
    brief: str
    platform: str
    brand_profile: dict
    brand_stats: dict
    learnings: list[dict]
    perf_stats: dict | None
    generate_image: bool
    brand_name: str
    # working data
    strategy: dict
    draft: str
    hashtags: list[str]
    first_draft: str
    critiques: list[dict]
    round: int
    verdict: str
    change_logs: list[list[str]]
    # outputs
    final_text: str
    image_prompt: str
    alt_text: str
    image_path: str | None
    editor_score: float
    trace: list[str]


class Sink(Protocol):
    """Where the pipeline records decisions and versions (the DB in production, a list in tests)."""

    def decision(self, *, agent: str, decision_type: str, summary: str, reasoning: str, payload: dict) -> None: ...

    def version(self, *, version: int, source: str, text: str, hashtags: list[str], editor_score: float | None, critique: dict) -> None: ...

    def status(self, status: str) -> None: ...


class ListSink:
    def __init__(self) -> None:
        self.decisions: list[dict] = []
        self.versions: list[dict] = []
        self.statuses: list[str] = []

    def decision(self, **kw: Any) -> None:
        self.decisions.append(kw)

    def version(self, **kw: Any) -> None:
        self.versions.append(kw)

    def status(self, status: str) -> None:
        self.statuses.append(status)


def _llm_info(mesh: MeshClient, before: int) -> list[dict]:
    """Model / token / latency of the gateway calls made since `before` (for the agent log)."""
    return [
        {"task": c.task, "model": c.model, "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens, "latency_ms": c.latency_ms}
        for c in mesh.calls[before:]
    ]


def build_graph(mesh: MeshClient, settings: Settings, sink: Sink, images_dir: Path):
    """Compile the LangGraph for one content piece."""

    # ------------------------------------------------------------- nodes
    def strategist_node(state: ContentState) -> dict:
        sink.status("strategist")
        n0 = len(mesh.calls)
        strategy = strategist_agent.run(
            mesh,
            brief=state["brief"],
            platform=state["platform"],
            brand_profile=state.get("brand_profile", {}),
            brand_stats=state.get("brand_stats", {}),
            learnings=state.get("learnings", []),
            perf_stats=state.get("perf_stats"),
            model=settings.mesh_chat_model,
        )
        sink.decision(
            agent="strategist",
            decision_type="angle_selected",
            summary=f"Angle: {strategy.get('angle', '')} | Hook ({strategy.get('hook_type', '?')}): {strategy.get('hook', '')}",
            reasoning=strategy.get("reasoning", ""),
            payload={**{k: v for k, v in strategy.items() if not k.startswith("_")}, "llm": _llm_info(mesh, n0)},
        )
        return {"strategy": strategy, "trace": state.get("trace", []) + ["strategist"]}

    def writer_node(state: ContentState) -> dict:
        sink.status("writer")
        n0 = len(mesh.calls)
        out = writer_agent.draft(
            mesh,
            brief=state["brief"],
            platform=state["platform"],
            strategy=state["strategy"],
            brand_profile=state.get("brand_profile", {}),
            brand_stats=state.get("brand_stats", {}),
            learnings=state.get("learnings", []),
            model=settings.mesh_chat_model,
        )
        sink.version(version=1, source="writer", text=out["draft"], hashtags=out["hashtags"], editor_score=None, critique={})
        sink.decision(
            agent="writer",
            decision_type="draft_written",
            summary=f"First draft: {len(out['draft'])} chars, {len(out['hashtags'])} hashtags",
            reasoning=out.get("notes", ""),
            payload={"learnings_applied": [lr.get("id") for lr in state.get("learnings", [])], "llm": _llm_info(mesh, n0)},
        )
        return {
            "draft": out["draft"],
            "first_draft": out["draft"],
            "hashtags": out["hashtags"],
            "round": 0,
            "critiques": [],
            "change_logs": [],
            "trace": state.get("trace", []) + ["writer"],
        }

    def editor_node(state: ContentState) -> dict:
        sink.status("editor")
        round_no = state.get("round", 0) + 1
        n0 = len(mesh.calls)
        crit = editor_agent.critique(
            mesh,
            platform=state["platform"],
            draft=state["draft"],
            strategy=state["strategy"],
            brand_profile=state.get("brand_profile", {}),
            learnings=state.get("learnings", []),
            round_no=round_no,
            pass_score=settings.editor_pass_score,
            model=settings.mesh_editor_model,
        )
        verdict = crit["verdict"]
        if verdict == "revise" and round_no > settings.editor_max_rounds:
            verdict = "accept_max_rounds"
        sink.decision(
            agent="editor",
            decision_type=f"review_round_{round_no}",
            summary=f"Round {round_no}: score {crit['score']:.1f}/10 → {verdict}. "
            + (f"{len(crit['required_edits'])} edits required." if crit["required_edits"] else "No edits required."),
            reasoning=crit.get("reasoning", ""),
            payload={**{k: crit.get(k) for k in ("score", "criteria", "issues", "required_edits", "praise", "facts")}, "llm": _llm_info(mesh, n0)},
        )
        return {
            "round": round_no,
            "verdict": verdict,
            "critiques": state.get("critiques", []) + [crit],
            "editor_score": crit["score"],
            "trace": state.get("trace", []) + [f"editor:{round_no}:{verdict}"],
        }

    def reviser_node(state: ContentState) -> dict:
        sink.status("revising")
        crit = state["critiques"][-1]
        n0 = len(mesh.calls)
        out = writer_agent.revise(
            mesh,
            platform=state["platform"],
            current_draft=state["draft"],
            critique=crit,
            strategy=state["strategy"],
            brand_profile=state.get("brand_profile", {}),
            learnings=state.get("learnings", []),
            model=settings.mesh_chat_model,
        )
        new_draft = out["draft"] or state["draft"]
        version_no = state["round"] + 1
        sink.version(
            version=version_no,
            source="revision",
            text=new_draft,
            hashtags=out["hashtags"] or state["hashtags"],
            editor_score=crit["score"],
            critique={k: crit.get(k) for k in ("score", "criteria", "issues", "required_edits")},
        )
        sink.decision(
            agent="writer",
            decision_type=f"revision_{state['round']}",
            summary=f"Revised draft after editor round {state['round']}: {len(out['change_log'])} changes, "
            f"{len(state['draft'])} → {len(new_draft)} chars",
            reasoning="; ".join(out["change_log"]) if out["change_log"] else "Applied the editor's required edits.",
            payload={"change_log": out["change_log"], "edits_requested": crit.get("required_edits", []), "llm": _llm_info(mesh, n0)},
        )
        return {
            "draft": new_draft,
            "hashtags": out["hashtags"] or state["hashtags"],
            "change_logs": state.get("change_logs", []) + [out["change_log"]],
            "trace": state.get("trace", []) + ["reviser"],
        }

    def visual_node(state: ContentState) -> dict:
        sink.status("visual")
        n0 = len(mesh.calls)
        plan = visual_agent.design(
            mesh,
            platform=state["platform"],
            text=state["draft"],
            strategy=state["strategy"],
            brand_profile=state.get("brand_profile", {}),
            model=settings.mesh_chat_model,
        )
        path, info = visual_agent.generate(
            mesh,
            plan=plan,
            platform=state["platform"],
            brand_name=state.get("brand_name", "CreatorOS"),
            out_path=images_dir / f"{state['content_id']}.png",
            use_image_model=state.get("generate_image", True),
        )
        how = (
            f"background from {mesh.image_model} + typeset headline"
            if info["image_model_used"]
            else ("procedural background (image model skipped) + typeset headline" if not state.get("generate_image", True)
                  else "procedural background (image model FAILED, see payload.error) + typeset headline")
        )
        sink.decision(
            agent="visual",
            decision_type="image_concept",
            summary=f"Visual ({plan.get('style', 'n/a')}, {plan.get('palette') or 'auto'} palette): headline \"{plan['headline']}\" — {how}",
            reasoning=plan.get("reasoning", ""),
            payload={
                "image_prompt": plan["image_prompt"], "headline": plan["headline"], "subline": plan.get("subline"),
                "palette": plan.get("palette"), "alt_text": plan["alt_text"], **info, "llm": _llm_info(mesh, n0),
            },
        )
        return {
            "image_prompt": plan["image_prompt"],
            "alt_text": plan["alt_text"],
            "image_path": str(path),
            "trace": state.get("trace", []) + ["visual"],
        }

    def finalize_node(state: ContentState) -> dict:
        sink.status("scoring")  # the coordinator sets 'ready' after scoring + the final write
        return {"final_text": state["draft"], "trace": state.get("trace", []) + ["finalize"]}

    # ------------------------------------------------------------- edges
    def after_editor(state: ContentState) -> str:
        return "reviser" if state.get("verdict") == "revise" else "visual"

    g: StateGraph = StateGraph(ContentState)
    g.add_node("strategist", strategist_node)
    g.add_node("writer", writer_node)
    g.add_node("editor", editor_node)
    g.add_node("reviser", reviser_node)
    g.add_node("visual", visual_node)
    g.add_node("finalize", finalize_node)

    g.set_entry_point("strategist")
    g.add_edge("strategist", "writer")
    g.add_edge("writer", "editor")
    g.add_conditional_edges("editor", after_editor, {"reviser": "reviser", "visual": "visual"})
    g.add_edge("reviser", "editor")  # the loop
    g.add_edge("visual", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
