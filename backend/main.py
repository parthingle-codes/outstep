"""OutStep FastAPI application.

API routes:
  GET  /api/health         -- liveness + which provider/model is configured
  GET  /api/config         -- non-secret config for the UI footer
  POST /api/generate-mission -- AI mission generation (validated before returning)
  GET  /api/sample-mission -- bundled sample mission, always labelled as a sample

In production the built frontend (`dist/`) is served from this same service.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import get_settings
from .providers import ProviderError, generate_mission, get_provider, sample_mission
from .schemas import (
    ActivityType,
    ConfigResponse,
    Difficulty,
    EnergyLevel,
    GenerateMissionResponse,
    HealthResponse,
    Mission,
    MissionRequest,
)
from .timing import summarize_run
from .validation import MissionValidationError

settings = get_settings()

app = FastAPI(title="OutStep API", version="0.1.0", description="AI outdoor mission generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- Errors -------------------------------------------------------------------

def _error(status: int, message: str, issues: list | None = None) -> JSONResponse:
    detail: dict = {"message": message}
    if issues:
        detail["issues"] = issues
    return JSONResponse(status_code=status, content={"detail": detail})


@app.exception_handler(ProviderError)
async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
    return _error(502, exc.message)


@app.exception_handler(MissionValidationError)
async def validation_error_handler(_request: Request, exc: MissionValidationError) -> JSONResponse:
    return _error(
        502,
        "The model returned a mission that failed safety or quality checks "
        "after several attempts. Try again, or switch models.",
        issues=exc.issues,
    )


# --- API routes ---------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", provider=settings.provider, model=settings.model_name)


@app.get("/api/config", response_model=ConfigResponse)
async def config() -> ConfigResponse:
    provider = get_provider(settings)
    return ConfigResponse(
        provider=settings.provider,
        provider_label=settings.provider_label,
        model=provider.model,
        sample_available=settings.allow_sample_mission,
    )


@app.post("/api/generate-mission", response_model=GenerateMissionResponse)
async def generate_mission_endpoint(request: MissionRequest) -> GenerateMissionResponse:
    """Generate a mission with the configured model and validate it before return."""
    mission = await generate_mission(request, provider=get_provider(settings))
    return GenerateMissionResponse(mission=mission)


@app.get("/api/sample-mission", response_model=GenerateMissionResponse)
async def sample_mission_endpoint(
    activity: ActivityType = ActivityType.explore_nature,
    duration_minutes: int = 30,
    energy: EnergyLevel = EnergyLevel.moderate,
    difficulty: Difficulty = Difficulty.steady,
    context: str = "",
):
    """Bundled sample mission for testing the UI without a model.

    Always `source: "sample"` so the frontend can label it as NOT AI-generated.
    """
    if not settings.allow_sample_mission:
        return _error(404, "Sample mission is disabled on this deployment.")
    try:
        request = MissionRequest(
            activity=activity,
            duration_minutes=duration_minutes,
            energy=energy,
            difficulty=difficulty,
            context=context,
        )
    except ValidationError as exc:
        issues = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return _error(422, "Invalid sample mission parameters.", issues=issues)
    return GenerateMissionResponse(mission=sample_mission(request))


@app.post("/api/summarize")
async def summarize(payload: dict) -> dict:
    """Helper mirroring the summary rules, so clients can reuse one implementation."""
    return summarize_run(
        task_statuses=payload.get("task_statuses", []),
        elapsed_ms=int(payload.get("elapsed_ms", 0)),
        planned_minutes=int(payload.get("planned_minutes", 0)),
    )


# --- Static frontend (production: one service serves API + UI) -----------------

DIST_DIR = Path(__file__).resolve().parent.parent / "dist"

if (DIST_DIR / "index.html").exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{spa_path:path}", include_in_schema=False, response_model=None)
    async def spa(spa_path: str) -> FileResponse | JSONResponse:
        # SPA fallback: unknown non-API paths get the app shell, but a missing
        # static asset is a real 404 (never HTML pretending to be JS/CSS).
        candidate = DIST_DIR / spa_path
        if spa_path and candidate.is_file():
            return FileResponse(candidate)
        if spa_path.startswith("assets/"):
            return _error(404, f"Asset not found: {spa_path}")
        return FileResponse(DIST_DIR / "index.html")
