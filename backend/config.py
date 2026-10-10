"""Environment-driven configuration for the OutStep backend.

All secrets live here, are read from the environment (or a local `.env` file),
and are NEVER returned to the browser. See `.env.example` for documentation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # optional: makes local `uvicorn backend.main:app` load `.env` automatically
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

VALID_PROVIDERS = ("ollama", "openai")
VALID_DURATIONS = (15, 30, 60)


def _split_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    allow_sample_mission: bool = True

    @property
    def provider_label(self) -> str:
        if self.provider == "ollama":
            return f"Ollama (local) · {self.ollama_model}"
        return f"OpenAI-compatible · {self.openai_model}"

    @property
    def model_name(self) -> str:
        return self.ollama_model if self.provider == "ollama" else self.openai_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = os.getenv("AI_PROVIDER", "ollama").strip().lower()
    if provider not in VALID_PROVIDERS:
        provider = "ollama"
    return Settings(
        provider=provider,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2").strip() or "llama3.2",
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        cors_origins=_split_origins(os.getenv("CORS_ORIGINS", "http://localhost:5173")),
        allow_sample_mission=os.getenv("ALLOW_SAMPLE_MISSION", "1") not in ("0", "false", "no"),
    )
