"""Replaceable AI provider layer.

Two providers ship with OutStep; add your own by implementing `BaseProvider`
and registering it in `get_provider`:

  * OllamaProvider        -- local development, fully offline (`ollama serve`)
  * OpenAICompatProvider  -- any remote endpoint exposing the OpenAI
                             `/v1/chat/completions` API (OpenAI, Groq, Together,
                             OpenRouter, vLLM, ...), configured via env vars.

API keys are read from the environment on the server and never reach the
browser. Providers raise `ProviderError` with a user-readable message when
inference fails; the API turns that into a clear 502 error for the UI.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings, get_settings
from .schemas import Mission, MissionRequest
from .validation import MissionValidationError, extract_json, raise_if_invalid, validate_mission

REQUEST_TIMEOUT_SECONDS = 120.0
MAX_ATTEMPTS = 2  # first attempt + one repair attempt driven by validation issues


class ProviderError(Exception):
    """Inference failed (unreachable endpoint, bad key, empty/broken response)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BaseProvider:
    """Minimal chat-completion interface. `name` and `model` are surfaced in the UI."""

    name = "base"
    model = "unknown"

    async def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, client: Optional[httpx.AsyncClient] = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.4},
        }
        try:
            async with (self._client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Ollama at {self.base_url} did not respond in time. "
                "The model may still be loading - try again in a moment."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Could not reach Ollama at {self.base_url}. "
                "Start it with `ollama serve` and pull a model, e.g. `ollama pull llama3.2`."
            ) from exc

        if response.status_code == 404:
            raise ProviderError(
                f"Model '{self.model}' is not available in Ollama. "
                f"Install it with `ollama pull {self.model}`."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            data = response.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Ollama returned an unexpected response shape.") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(f"Model '{self.model}' returned an empty response.")
        return content


class OpenAICompatProvider(BaseProvider):
    name = "openai"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = client

    async def complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with (self._client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"The endpoint at {self.base_url} did not respond in time."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Could not reach the endpoint at {self.base_url}. Check OPENAI_BASE_URL."
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderError("The endpoint rejected the API key. Check OPENAI_API_KEY.")
        if response.status_code == 404:
            raise ProviderError(
                f"Model '{self.model}' was not found at {self.base_url}. Check OPENAI_MODEL."
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"The endpoint returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("The endpoint returned an unexpected response shape.") from exc
        if isinstance(content, list):  # some providers return content parts
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(f"Model '{self.model}' returned an empty response.")
        return content


def get_provider(settings: Optional[Settings] = None) -> BaseProvider:
    """Factory: which provider to use is an environment decision, never code."""
    settings = settings or get_settings()
    if settings.provider == "openai":
        return OpenAICompatProvider(
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
        )
    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)


# --- Prompting ---------------------------------------------------------------

SYSTEM_PROMPT = """You are OutStep's mission planner: an upbeat outdoor guide who designs short,
achievable missions for real people in ordinary public places (parks, streets, gardens,
beaches, courtyards). You write for someone who wants to spend time away from their screen.

STRICT OUTPUT RULES
- Reply with ONE JSON object and nothing else. No markdown, no commentary.
- The JSON must match this schema exactly:
  {
    "title": string (3-80 chars, motivating),
    "description": string (10-500 chars, what the mission feels like),
    "total_duration_minutes": integer,
    "tasks": [
      {"instruction": string (10-280 chars), "target_minutes": integer,
       "completion_mode": "manual" | "timer"}
    ],
    "completion_mode": "manual" | "timer",
    "safety_notes": [string (5-200 chars each)]
  }
- "completion_mode" meaning: "manual" = the person taps Done when finished;
  "timer" = the app shows a simple countdown for that task.
- tasks: exactly 3 to 5 items, each 1-45 minutes, and they must add up to
  roughly the requested total (between 60% and 140% of it).
- total_duration_minutes MUST equal the requested duration.

SAFETY AND SUITABILITY (hard rules)
- Every task must be doable outdoors, in public, with no special equipment.
- NEVER suggest trespassing, private property, railway tracks, roads/freeways,
  traffic, climbing cliffs/roofs, unsafe swimming, weapons, fire, alcohol,
  drugs, or entering buildings.
- Prefer public paths, parks, sidewalks, and well-used areas.
- Always include 1-3 concrete safety notes (water, sun, crossings, footwear,
  staying on public paths).
- Time is a guide: phrase tasks so they can be shortened or skipped, and never
  make a task a race.
"""


def build_user_prompt(request: MissionRequest) -> str:
    lines = [
        f"Activity: {request.activity.value.replace('_', ' ')}",
        f"Duration: {request.duration_minutes} minutes",
        f"Energy level: {request.energy.value}",
        f"Difficulty: {request.difficulty.value}",
    ]
    if request.context:
        lines.append(f"Extra context from the user: {request.context}")
    lines.append("Design the mission now. Reply with the JSON object only.")
    return "\n".join(lines)


# --- Generation with validation + one repair retry ---------------------------

async def generate_mission(
    request: MissionRequest,
    provider: Optional[BaseProvider] = None,
) -> Mission:
    """Generate, validate, (optionally repair), and return a safe mission.

    Raises ProviderError when inference fails and MissionValidationError when
    the model output cannot be made valid. Never returns a fallback mission.
    """
    provider = provider or get_provider()
    user_prompt = build_user_prompt(request)
    issues: List[dict] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = user_prompt
        if issues:
            feedback = "\n\nYour previous reply was rejected for these reasons:\n" + "\n".join(
                f"- {i['field']}: {i['message']}" for i in issues
            )
            prompt += feedback + "\nReply again with ONLY the corrected JSON object."
        raw_text = await provider.complete(SYSTEM_PROMPT, prompt)
        data, json_error = extract_json(raw_text)
        if data is None:
            issues = [{"field": "root", "message": json_error or "invalid JSON"}]
            continue

        result = validate_mission(data, request)
        if result.ok and result.mission is not None:
            mission = result.mission
            mission.source = "ai"
            mission.provider = provider.name
            mission.model = provider.model
            from datetime import datetime, timezone

            mission.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return mission
        issues = result.issues

    raise MissionValidationError(issues)


# --- Bundled sample (explicitly NOT AI output) --------------------------------

def sample_mission(request: Optional[MissionRequest] = None) -> Mission:
    from .validation import build_sample_mission

    return build_sample_mission(request)
