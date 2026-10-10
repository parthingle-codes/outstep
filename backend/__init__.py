"""OutStep backend package.

Modules:
    config       -- environment-driven configuration (provider, model, keys)
    schemas      -- Pydantic models for API requests/responses (the mission schema)
    validation   -- deterministic validation of model output + safety checks
    timing       -- pure time math used for mission/task tracking (mirrored in JS)
    providers    -- replaceable AI providers (Ollama, OpenAI-compatible)
    main         -- FastAPI app: API routes + serving the built frontend
"""
