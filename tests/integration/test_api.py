"""End-to-end API tests through FastAPI's TestClient (SQLite + mock Mesh)."""

from datetime import datetime, timedelta, timezone


def test_health_and_platforms(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and "meshapi.ai" in h["mesh_base_url"]
    assert {p["key"] for p in client.get("/api/platforms").json()} == {"linkedin", "x", "instagram", "blog"}


def test_brand_voice_learned_from_samples(client, seeded_brand):
    assert seeded_brand["sample_count"] >= 3
    assert seeded_brand["profile"]["summary"]
    assert seeded_brand["profile_stats"]["samples"] == seeded_brand["sample_count"]
    decisions = client.get(f"/api/decisions?brand_id={seeded_brand['id']}&agent=brand").json()
    assert decisions and decisions[0]["decision_type"] == "voice_profile_learned"


def test_brand_validation(client):
    r = client.post("/api/brands", json={"name": "Solo", "samples": [{"text": "only one sample of twenty+ chars"}]})
    assert r.status_code == 201 and r.json()["profile"] == {}  # not enough samples → no profile yet
    bid = r.json()["id"]
    assert client.post(f"/api/brands/{bid}/learn-voice").status_code == 400
    r = client.post(f"/api/brands/{bid}/samples", json={"samples": [{"text": "a second sample that is long enough"}]})
    assert r.json()["profile"]["summary"]
    assert client.post("/api/brands", json={"name": "Solo"}).status_code == 409


def _make(client, brand_id, brief="a LinkedIn post about AI safety", platforms=("linkedin",)):
    r = client.post("/api/content?wait=true", json={"brand_id": brand_id, "brief": brief, "platforms": list(platforms)})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_generation_pipeline(client, seeded_brand):
    piece = _make(client, seeded_brand["id"])[0]
    assert piece["status"] == "ready"
    assert piece["editor_rounds"] >= 1 and piece["final_editor_score"] >= 7.5
    assert piece["quality_before"] is not None and piece["quality_after"] is not None
    assert piece["image_url"] and client.get(piece["image_url"]).headers["content-type"] == "image/png"
    detail = client.get(f"/api/content/{piece['id']}").json()
    assert len(detail["versions"]) >= 2 and detail["versions"][0]["text"] != detail["versions"][-1]["text"]
    types = [d["decision_type"] for d in detail["decisions"]]
    assert "angle_selected" in types and "review_round_1" in types and "image_concept" in types and "quality_scored" in types
    assert all(d["content_id"] == piece["id"] for d in detail["decisions"])


def test_multi_platform_campaign_adapts_per_platform(client, seeded_brand):
    pieces = _make(client, seeded_brand["id"], brief="one idea, many platforms", platforms=("linkedin", "x"))
    assert len(pieces) == 2 and len({p["campaign_id"] for p in pieces}) == 1 and pieces[0]["campaign_id"]
    x = next(p for p in pieces if p["platform"] == "x")
    assert len(x["final_text"]) <= 280


def test_invalid_platform_rejected(client, seeded_brand):
    r = client.post("/api/content", json={"brand_id": seeded_brand["id"], "brief": "hello world", "platforms": ["tiktok"]})
    assert r.status_code == 400


def test_schedule_publish_feedback_learn_loop(client, seeded_brand):
    bid = seeded_brand["id"]
    a = _make(client, bid, brief="first post about gateways")[0]
    b = _make(client, bid, brief="second post about clusters")[0]

    # schedule a → due in the past → scheduler publishes it
    when = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = client.post(f"/api/content/{a['id']}/schedule", json={"scheduled_at": when})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    assert client.post("/api/scheduler/run").json()["published"] >= 1
    a2 = client.get(f"/api/content/{a['id']}").json()
    assert a2["status"] == "published" and a2["performance"] and a2["performance"][0]["source"] == "simulated"

    # publish b now, then user-entered performance
    assert client.post(f"/api/content/{b['id']}/publish").json()["status"] == "published"
    r = client.post(f"/api/content/{b['id']}/performance", json={"impressions": 5000, "likes": 300, "comments": 40, "shares": 25})
    assert r.status_code == 200 and r.json()["latest_engagement"] > 0
    assert client.post(f"/api/content/{a['id']}/performance", json={"likes": 1}).status_code == 200

    # cannot record performance on an unpublished piece
    c = _make(client, bid, brief="third, unpublished")[0]
    assert client.post(f"/api/content/{c['id']}/performance", json={"likes": 1}).status_code == 400

    # learning cycle
    r = client.post(f"/api/brands/{bid}/learn", json={"platform": "linkedin"})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["pieces_analysed"] >= 2 and "hook_type" in run["stats"]
    learnings = client.get(f"/api/brands/{bid}/learnings").json()
    assert learnings and all(l["active"] and l["rule"] for l in learnings)
    assert client.get(f"/api/brands/{bid}/learning-runs").json()[0]["id"] == run["id"]
    learner_decisions = client.get(f"/api/decisions?brand_id={bid}&agent=learner").json()
    assert learner_decisions and learner_decisions[0]["payload"]["run_id"] == run["id"]

    # the next piece has the learnings injected → closed loop
    d = _make(client, bid, brief="fourth post, after learning")[0]
    assert set(d["learnings_applied"]) == {l["id"] for l in learnings}
    assert client.get(f"/api/content/{d['id']}").json()["decisions"][1]["payload"]["learnings_applied"] == d["learnings_applied"]

    # a second cycle supersedes the first
    client.post(f"/api/brands/{bid}/learn", json={"platform": "linkedin"})
    all_l = client.get(f"/api/brands/{bid}/learnings?include_inactive=true").json()
    assert len([l for l in all_l if not l["active"]]) >= len(learnings)


def test_learning_needs_two_pieces(client, second_brand):
    r = client.post(f"/api/brands/{second_brand['id']}/learn", json={"platform": "instagram"})
    assert r.status_code == 400


def test_different_brands_produce_different_prompts_context(client, seeded_brand, second_brand):
    # Both brands have learned profiles that differ (emoji usage, tone) — checked at the profile level.
    assert seeded_brand["profile_stats"]["emoji_per_post"] < second_brand["profile_stats"]["emoji_per_post"]


def test_stats_and_regenerate(client, seeded_brand):
    s = client.get("/api/stats").json()
    assert s["pieces"] >= 1 and s["decisions"] > 0 and s["avg_quality_after"] is not None
    src = client.get("/api/content?limit=1").json()[0]
    r = client.post(f"/api/content/{src['id']}/regenerate?wait=true")
    assert r.status_code == 200 and r.json()["status"] == "ready" and r.json()["brief"] == src["brief"]
    assert client.get("/api/content/nope").status_code == 404


def test_visual_is_always_produced_and_logged(client, seeded_brand):
    piece = _make(client, seeded_brand["id"], brief="visual check post")[0]
    assert piece["image_url"]
    d = client.get(f"/api/content/{piece['id']}").json()
    vis = next(x for x in d["decisions"] if x["decision_type"] == "image_concept")
    assert vis["payload"]["headline"] and vis["payload"]["image_model_used"] is True
    assert vis["payload"]["llm"] and vis["payload"]["llm"][0]["model"]
    # every agent decision carries the gateway call it made
    for dec in d["decisions"]:
        if dec["agent"] in ("strategist", "writer", "editor"):
            assert dec["payload"]["llm"][0]["task"]
    # skipping the image model still yields a poster
    r = client.post("/api/content?wait=true", json={"brand_id": seeded_brand["id"], "brief": "no image model please", "platforms": ["x"], "generate_image": False})
    p2 = r.json()[0]
    assert p2["image_url"] and client.get(p2["image_url"]).status_code == 200
    vis2 = next(x for x in client.get(f"/api/content/{p2['id']}").json()["decisions"] if x["decision_type"] == "image_concept")
    assert vis2["payload"]["image_model_used"] is False


def test_best_slot_endpoint_and_schedule_reason(client, seeded_brand):
    piece = _make(client, seeded_brand["id"], brief="slot check")[0]
    rec = client.get(f"/api/content/{piece['id']}/best-slot").json()
    assert rec["basis"] in ("platform_default", "performance") and rec["reason"]
    r = client.post(f"/api/content/{piece['id']}/schedule", json={"scheduled_at": rec["scheduled_at"], "reason": "Accepted recommended slot: " + rec["reason"]})
    assert r.status_code == 200
    sched = [d for d in client.get(f"/api/content/{piece['id']}").json()["decisions"] if d["agent"] == "scheduler"][-1]
    assert sched["reasoning"].startswith("Accepted recommended slot")


def test_example_brief_exposed_for_demo_brands(client, seeded_brand):
    assert seeded_brand["example_brief"] and seeded_brand["example_platforms"]
