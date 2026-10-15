"""Shared fixtures. Tests run fully offline: MESH_MOCK=1 makes the Mesh client return deterministic
canned responses, and the database is a throw-away SQLite file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="creatoros-test-"))
os.environ.setdefault("MESH_MOCK", "1")
os.environ.setdefault("MESH_API_KEY", "")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["LOG_LEVEL"] = "WARNING"


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def seeded_brand(client) -> dict:
    r = client.post("/api/demo/seed")
    assert r.status_code == 200, r.text
    brands = r.json()["brands"]
    return next(b for b in brands if b["name"] == "Techsivam Labs")


@pytest.fixture(scope="session")
def second_brand(client, seeded_brand) -> dict:
    return next(b for b in client.get("/api/brands").json() if b["name"] == "Sunny Side Bakes")


@pytest.fixture
def mesh():
    from app.mesh import MeshClient

    return MeshClient(api_key="", mock=True)
