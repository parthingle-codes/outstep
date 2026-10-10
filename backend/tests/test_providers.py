"""Provider tests using httpx.MockTransport (no network, no real model)."""

import asyncio
import json

import httpx
import pytest

from backend.providers import (
    OllamaProvider,
    OpenAICompatProvider,
    ProviderError,
    build_user_prompt,
)
from backend.schemas import MissionRequest


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
