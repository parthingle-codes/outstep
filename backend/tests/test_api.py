"""API-level tests: endpoints, error handling, and generation with a fake model."""

import asyncio
import json

from fastapi.testclient import TestClient

import backend.main as main
from backend.archetypes import ARCHETYPE_IDS
from backend.config import Settings
from backend.main import app
from backend.providers import BaseProvider, ProviderError
from backend.validation import build_sample_mission

client = TestClient(app, raise_server_exceptions=False)


class FakeGoodProvider(BaseProvider):
    """Returns one valid mission JSON, like a well-behaved model."""

    name = "fake"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.responses.pop(0)


def valid_mission_json(duration=30, **overrides):
    from backend.schemas import MissionRequest

    request = MissionRequest(activity="explore_nature", duration_minutes=duration)
    payload = build_sample_mission(request).model_dump()
    payload.pop("source", None)
    payload.update(overrides)
    return json.dumps(payload)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] in ("ollama", "openai")


def test_config_hides_secrets():
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"provider", "provider_label", "model", "sample_available"}
    assert "key" not in json.dumps(body).lower()


def test_sample_mission_is_labelled():
    response = client.get("/api/sample-mission")
    assert response.status_code == 200
    mission = response.json()["mission"]
    assert mission["source"] == "sample"
    assert 3 <= len(mission["tasks"]) <= 5
    assert mission["safety_notes"]


def test_sample_mission_accepts_query_params():
    response = client.get("/api/sample-mission?duration_minutes=15&activity=move")
    assert response.status_code == 200, response.text
    mission = response.json()["mission"]
    assert mission["source"] == "sample"
    assert mission["total_duration_minutes"] == 15


def test_sample_mission_rejects_bad_duration():
    response = client.get("/api/sample-mission?duration_minutes=20")
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "Invalid sample mission parameters."


def test_generate_rejects_invalid_duration():
    response = client.post(
        "/api/generate-mission",
        json={"activity": "move", "duration_minutes": 20},
    )
    assert response.status_code == 422


def test_generate_with_fake_model_succeeds(monkeypatch):
    provider = FakeGoodProvider([valid_mission_json()])
    monkeypatch.setattr(main, "get_provider", lambda *a, **k: provider)
    response = client.post(
        "/api/generate-mission",
        json={"activity": "observe", "duration_minutes": 30, "energy": "low"},
    )
    assert response.status_code == 200, response.text
    mission = response.json()["mission"]
    assert mission["source"] == "ai"
    assert mission["provider"] == "fake"
    assert mission["model"] == "fake-model"
    assert mission["generated_at"]
    assert 3 <= len(mission["tasks"]) <= 5


def test_generate_repairs_on_second_attempt(monkeypatch):
    bad = json.dumps({"title": "Ok title here", "tasks": []})  # invalid on purpose
    provider = FakeGoodProvider([bad, valid_mission_json(duration=15)])
    monkeypatch.setattr(main, "get_provider", lambda *a, **k: provider)
    response = client.post(
        "/api/generate-mission",
        json={"activity": "move", "duration_minutes": 15},
    )
    assert response.status_code == 200, response.text
    assert provider.calls == 2


def test_generate_fails_clearly_when_model_keeps_returning_junk(monkeypatch):
    provider = FakeGoodProvider(["not json at all"] * 3)
    monkeypatch.setattr(main, "get_provider", lambda *a, **k: provider)
    response = client.post(
        "/api/generate-mission",
        json={"activity": "move", "duration_minutes": 15},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "failed safety or quality checks" in detail["message"]
    assert detail["issues"]


def test_generate_reports_provider_failure(monkeypatch):
    class BrokenProvider(BaseProvider):
        name = "broken"
        model = "broken-model"

        async def complete(self, system, user):
            raise ProviderError("Could not reach Ollama at http://localhost:11434.")

    monkeypatch.setattr(main, "get_provider", lambda *a, **k: BrokenProvider())
    response = client.post(
        "/api/generate-mission",
        json={"activity": "explore_nature", "duration_minutes": 60},
    )
    assert response.status_code == 502
    assert "Could not reach Ollama" in response.json()["detail"]["message"]


def test_unreachable_endpoint_returns_clear_error(monkeypatch):
    # Point the real factory at a closed port: connection refused -> clear 502.
    monkeypatch.setattr(
        main,
        "settings",
        Settings(provider="openai", openai_base_url="http://127.0.0.1:9/v1", openai_model="x"),
    )
    response = client.post(
        "/api/generate-mission",
        json={"activity": "explore_nature", "duration_minutes": 15},
    )
    assert response.status_code == 502
    assert "Could not reach" in response.json()["detail"]["message"]


def test_generate_response_includes_objective_and_archetype(monkeypatch):
    provider = FakeGoodProvider([valid_mission_json()])
    monkeypatch.setattr(main, "get_provider", lambda *a, **k: provider)
    response = client.post(
        "/api/generate-mission",
        json={"activity": "explore_nature", "duration_minutes": 30},
    )
    assert response.status_code == 200, response.text
    mission = response.json()["mission"]
    assert mission["objective"]
    assert mission["archetype"] in ARCHETYPE_IDS


def test_sample_mission_includes_objective_and_archetype():
    response = client.get("/api/sample-mission")
    assert response.status_code == 200
    mission = response.json()["mission"]
    assert mission["objective"]
    assert mission["archetype"] == "micro_explorer"


def test_summarize_endpoint_mirrors_timing_rules():
    response = client.post(
        "/api/summarize",
        json={"task_statuses": ["completed", "skipped"], "elapsed_ms": 20 * 60_000, "planned_minutes": 15},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["completed"] == 1
    assert body["past_planned"] is True
    assert "failed" not in body
