"""Provider tests using httpx.MockTransport (no network, no real model)."""

import asyncio
import json

import httpx
import pytest

from backend.providers import (
    MAX_ATTEMPTS,
    SYSTEM_PROMPT,
    BaseProvider,
    OllamaProvider,
    OpenAICompatProvider,
    ProviderError,
    build_user_prompt,
    generate_mission,
)
from backend.schemas import MissionArchetype, MissionRequest
from backend.validation import MissionValidationError


def run(coro):
    return asyncio.run(coro)


def test_openai_provider_sends_messages_and_returns_content():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"title": "hi"}'}}]},
        )

    provider = OpenAICompatProvider(
        base_url="https://example.test/v1",
        model="my-model",
        api_key="secret-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    text = run(provider.complete("system prompt", "user prompt"))
    assert text == '{"title": "hi"}'
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer secret-key"
    assert captured["body"]["model"] == "my-model"
    assert captured["body"]["messages"][0]["content"] == "system prompt"


def test_openai_provider_wrong_key_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    provider = OpenAICompatProvider(
        base_url="https://example.test/v1",
        model="m",
        api_key="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as exc:
        run(provider.complete("s", "u"))
    assert "API key" in str(exc.value)


def test_openai_provider_missing_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    provider = OpenAICompatProvider(
        base_url="https://example.test/v1",
        model="nope",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as exc:
        run(provider.complete("s", "u"))
    assert "OPENAI_MODEL" in str(exc.value)


def test_openai_provider_unreachable_endpoint():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        model="m",
        client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
    )
    with pytest.raises(ProviderError) as exc:
        run(provider.complete("s", "u"))
    assert "Could not reach" in str(exc.value)


def test_openai_provider_content_parts_supported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"type": "text", "text": "part1"}]}}]},
        )

    provider = OpenAICompatProvider(
        base_url="https://example.test/v1",
        model="m",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert run(provider.complete("s", "u")) == "part1"


def test_ollama_provider_request_shape_and_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": '{"ok": true}'} })

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3.2",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    text = run(provider.complete("sys", "usr"))
    assert text == '{"ok": true}'
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["stream"] is False
    assert captured["body"]["format"] == "json"
    assert captured["body"]["model"] == "llama3.2"


def test_ollama_provider_missing_model_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="ghost",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as exc:
        run(provider.complete("s", "u"))
    assert "ollama pull ghost" in str(exc.value)


def test_ollama_provider_empty_response_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "  "}})

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="m",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as exc:
        run(provider.complete("s", "u"))
    assert "empty response" in str(exc.value)


def test_build_user_prompt_includes_preferences():
    request = MissionRequest(
        activity="clear_my_head",
        duration_minutes=60,
        energy="high",
        difficulty="chill",
        context="I'm bringing my dog",
    )
    prompt = build_user_prompt(request)
    assert "clear my head" in prompt
    assert "60 minutes" in prompt
    assert "high" in prompt
    assert "dog" in prompt


def test_build_user_prompt_includes_archetype():
    from backend.archetypes import get_archetype

    request = MissionRequest(activity="observe", duration_minutes=30)
    prompt = build_user_prompt(request, get_archetype("sound_mapper"))
    assert "Sound Mapper" in prompt
    assert "sound_mapper" in prompt
    # The brief tells the model what the style looks like in practice.
    assert "cartographer" in prompt.lower()


def test_system_prompt_demands_creative_structure():
    from backend.providers import SYSTEM_PROMPT

    assert "archetype" in SYSTEM_PROMPT
    assert "objective" in SYSTEM_PROMPT
    assert "rewordings" in SYSTEM_PROMPT
    assert "notice your surroundings" in SYSTEM_PROMPT  # listed as banned filler
    assert "concrete objective" in SYSTEM_PROMPT
    assert "EXACTLY the requested total" in SYSTEM_PROMPT


def _valid_payload_json():
    import json

    from backend.schemas import MissionRequest as _MissionRequest
    from backend.validation import build_sample_mission

    payload = build_sample_mission(_MissionRequest(activity="explore_nature", duration_minutes=30))
    data = payload.model_dump()
    data.pop("source", None)
    return json.dumps(data)


def test_generate_mission_selects_archetype_and_stamps_it():
    captured = {}

    class CapturingProvider(BaseProvider):
        name = "capture"
        model = "capture-model"

        async def complete(self, system, user):
            captured["system"] = system
            captured["user"] = user
            return _valid_payload_json()

    request = MissionRequest(activity="explore_nature", duration_minutes=30)
    mission = run(generate_mission(request, provider=CapturingProvider()))

    assert mission.archetype in MissionArchetype
    assert mission.objective
    # The selected archetype drives the prompt and is echoed in the user message.
    assert mission.archetype.value in captured["user"]
    assert captured["system"] == SYSTEM_PROMPT


def test_generate_mission_honours_an_explicit_archetype():
    captured = {}

    class CapturingProvider(BaseProvider):
        name = "capture"
        model = "capture-model"

        async def complete(self, system, user):
            captured["user"] = user
            return _valid_payload_json()

    from backend.archetypes import get_archetype

    spec = get_archetype("urban_archaeologist")
    request = MissionRequest(activity="observe", duration_minutes=30)
    mission = run(generate_mission(request, provider=CapturingProvider(), archetype=spec))

    assert mission.archetype is MissionArchetype.urban_archaeologist
    assert "Urban Archaeologist" in captured["user"]


def test_generate_mission_repair_feedback_names_the_generic_tasks():
    """When the model pads with filler, the retry prompt says exactly what to fix."""
    import json

    generic = {
        "title": "Neighbourhood Wind-Down",
        "description": "A gentle loop around your local streets with time to breathe.",
        "objective": "Finish the walk feeling calmer than when you started out today.",
        "total_duration_minutes": 30,
        "tasks": [
            {"instruction": "Take a slow walk through the park and enjoy the fresh air.",
             "target_minutes": 8},
            {"instruction": "Notice your surroundings and appreciate the small details.",
             "target_minutes": 8},
            {"instruction": "Listen to the sounds of nature around you.",
             "target_minutes": 7},
            {"instruction": "Relax and take a deep breath before heading home.",
             "target_minutes": 7},
        ],
        "safety_notes": ["Stay on public paths and watch for cyclists."],
    }

    class RepairProvider(BaseProvider):
        name = "repair"
        model = "repair-model"

        def __init__(self):
            self.prompts = []

        async def complete(self, system, user):
            self.prompts.append(user)
            if len(self.prompts) == 1:
                return json.dumps(generic)
            return _valid_payload_json()

    provider = RepairProvider()
    request = MissionRequest(activity="explore_nature", duration_minutes=30)
    mission = run(generate_mission(request, provider=provider))

    assert len(provider.prompts) == 2
    repair_prompt = provider.prompts[1]
    assert "rejected" in repair_prompt
    assert "concrete objective" in repair_prompt


def test_generate_mission_gives_up_after_max_attempts():
    class AlwaysGenericProvider(BaseProvider):
        name = "filler"
        model = "filler-model"

        def __init__(self):
            self.calls = 0

        async def complete(self, system, user):
            self.calls += 1
            import json

            return json.dumps(
                {
                    "title": "Neighbourhood Wind-Down Loop",
                    "description": "A gentle loop around your local streets with time.",
                    "objective": "Finish the walk feeling calmer than when you started.",
                    "total_duration_minutes": 30,
                    "tasks": [
                        {"instruction": "Take a slow walk through the park and breathe.",
                         "target_minutes": 10},
                        {"instruction": "Notice your surroundings and the small details.",
                         "target_minutes": 10},
                        {"instruction": "Listen to the sounds of nature around you.",
                         "target_minutes": 10},
                    ],
                    "safety_notes": ["Stay on public paths and watch for cyclists."],
                }
            )

    provider = AlwaysGenericProvider()
    request = MissionRequest(activity="explore_nature", duration_minutes=30)
    with pytest.raises(MissionValidationError):
        run(generate_mission(request, provider=provider))
    assert provider.calls == MAX_ATTEMPTS
