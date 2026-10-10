"""Deterministic validation of AI-generated missions.

The model is free to write whatever it likes; nothing reaches the user unless
it passes the checks in this module:

  * schema shape (3-5 tasks, ids, modes, durations)
  * sensible timing (each task 1-45 min, per-task targets that add up plausibly
    to the requested total)
  * public-outdoor suitability (no indoor tasks)
  * safety (no trespassing, roads/railways, dangerous or illegal activities)

Issues are collected (not raised on first failure) so one model retry can fix
everything at once.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .config import VALID_DURATIONS
from .schemas import ActivityType, CompletionMode, Difficulty, EnergyLevel, Mission, MissionRequest, MissionTask

# --- Safety scan -------------------------------------------------------------

# Each entry: (regex, human-readable reason). Scanned over title, description
# and task instructions (not safety notes, which legitimately mention hazards).
DANGEROUS_PATTERNS: List[Tuple[str, str]] = [
    (r"\btrespass", "encourages trespassing"),
    (r"private propert", "refers to entering private property"),
    (r"\brailway\b|\brailroad\b|train tracks?", "involves railway tracks"),
    (r"\bfreeway\b|\bhighway\b|\binterstate\b", "involves a high-speed road"),
    (r"\btraffic\b|into traffic|in traffic", "involves moving traffic"),
    (r"swim\w* alone|unsupervised swim|deep water|open water", "involves unsafe swimming"),
    (r"\bcliff|ravine|\bquarry\b|mine shaft|gorge edge", "involves dangerous terrain"),
    (r"rooftop|roof top|onto the roof", "involves a rooftop"),
    (r"\bweapon|\bgun\b|\bknif", "involves a weapon"),
    (r"campfire|open fire|bonfire|firework|arson", "involves fire"),
    (r"\balcohol|\bdrugs?\b|\bdrinking\b", "involves alcohol or drugs"),
    (r"\babandoned\b", "involves abandoned structures"),
    (r"enter (a|an|the|any) (building|house|structure|property)", "involves entering a structure"),
    (r"dark alley|\bmugging\b|\billegal\b", "involves an unsafe or illegal act"),
    (r"jump(ing)? (off|from|onto|into) (a |the )?(bridge|roof|cliff|moving)", "involves dangerous jumping"),
]

# Tasks must be doable outdoors; these point to indoor/phone-only tasks.
INDOOR_PATTERNS: List[Tuple[str, str]] = [
    (r"\bindoors?\b", "reads as an indoor task"),
    (r"\bat home\b|\bin your (room|house|home|kitchen|bedroom|living room)\b", "reads as an indoor task"),
    (r"\bsit at your desk\b|\bon your couch\b", "reads as an indoor task"),
]

# Common ways models phrase the completion mode.
MODE_SYNONYMS = {
    "manual": "manual",
    "manual confirmation": "manual",
    "confirm": "manual",
    "confirmation": "manual",
    "self-reported": "manual",
    "tap when done": "manual",
    "timer": "timer",
    "simple timer": "timer",
    "timed": "timer",
    "countdown": "timer",
}


class MissionValidationError(Exception):
    """The model output could not be validated. `issues` is user-displayable."""

    def __init__(self, issues: List[dict]):
        self.issues = issues
        summary = "; ".join(f"{i['field']}: {i['message']}" for i in issues[:5])
        if len(issues) > 5:
            summary += f" (+{len(issues) - 5} more)"
        super().__init__(summary)


@dataclass
class ValidationResult:
    mission: Optional[Mission] = None
    issues: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.mission is not None and not self.issues


# --- JSON extraction ---------------------------------------------------------

def extract_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """Pull a JSON object out of a model response.

    Handles raw JSON, ```json fences, and surrounding prose.
    Returns (data, error_message).
    """
    if not text or not text.strip():
        return None, "the model returned an empty response"
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return None, "the model did not return a JSON object"
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"the model returned invalid JSON ({exc.msg})"
    if not isinstance(data, dict):
        return None, "the model returned JSON that is not an object"
    return data, None


def _clean_text(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.match(r"^\s*(\d+)", value)
        if match:
            return int(match.group(1))
    return None


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, list):
        return [_clean_text(v) for v in value if _clean_text(v)]
    return []


def normalize_mode(value: Any, default: CompletionMode) -> CompletionMode:
    text = _clean_text(value).lower()
    if not text:
        return default
    if text in MODE_SYNONYMS:
        return CompletionMode(MODE_SYNONYMS[text])
    for synonym, mode in MODE_SYNONYMS.items():
        if synonym in text:
            return CompletionMode(mode)
    return default


# --- The validator -----------------------------------------------------------

def validate_mission(raw: Any, request: MissionRequest) -> ValidationResult:
    """Validate raw model output against `request`.

    Returns a `ValidationResult`; `result.mission` is set only when the payload
    is safe and usable. Non-fatal normalizations are recorded in `warnings`.
    """
    issues: List[dict] = []
    warnings: List[str] = []

    if not isinstance(raw, dict):
        issues.append({"field": "root", "message": "model output must be a JSON object"})
        return ValidationResult(issues=issues)

    # --- title / description -------------------------------------------------
    title = _clean_text(raw.get("title"))
    if len(title) < 3:
        issues.append({"field": "title", "message": "title must be at least 3 characters"})
    elif len(title) > 80:
        title = title[:80]
        warnings.append("title was shortened to 80 characters")

    description = _clean_text(raw.get("description"))
    if len(description) < 10:
        issues.append({"field": "description", "message": "description must be at least 10 characters"})
    elif len(description) > 500:
        description = description[:500]
        warnings.append("description was shortened to 500 characters")

    # --- total duration ------------------------------------------------------
    total = _as_int(raw.get("total_duration_minutes"))
    if total is None:
        issues.append({"field": "total_duration_minutes", "message": "must be an integer number of minutes"})
    else:
        if total not in VALID_DURATIONS:
            issues.append(
                {"field": "total_duration_minutes", "message": f"must be one of {list(VALID_DURATIONS)}"}
            )
        elif total != request.duration_minutes:
            warnings.append(
                f"model planned {total} min; using the requested {request.duration_minutes} min"
            )
            total = request.duration_minutes

    # --- completion mode -----------------------------------------------------
    default_mode = normalize_mode(raw.get("completion_mode"), CompletionMode.manual)

    # --- tasks ---------------------------------------------------------------
    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list):
        issues.append({"field": "tasks", "message": "must be a list of 3-5 tasks"})
        tasks_raw = []
    elif not (3 <= len(tasks_raw) <= 5):
        issues.append({"field": "tasks", "message": f"must contain 3-5 tasks (got {len(tasks_raw)})"})

    tasks: List[MissionTask] = []
    target_sum = 0
    for idx, item in enumerate(tasks_raw, start=1):
        label = f"tasks[{idx}]"
        if not isinstance(item, dict):
            issues.append({"field": label, "message": "each task must be an object"})
            continue

        instruction = _clean_text(item.get("instruction"))
        if len(instruction) < 10:
            issues.append({"field": f"{label}.instruction", "message": "instruction is too short"})
        elif len(instruction) > 280:
            instruction = instruction[:280]
            warnings.append(f"task {idx} instruction shortened to 280 characters")

        minutes_raw = (
            item["target_minutes"] if "target_minutes" in item else item.get("duration_minutes")
        )
        minutes = _as_int(minutes_raw)
        if minutes is None:
            issues.append({"field": f"{label}.target_minutes", "message": "must be an integer number of minutes"})
        elif not (1 <= minutes <= 45):
            issues.append(
                {"field": f"{label}.target_minutes", "message": "must be between 1 and 45 minutes"}
            )

        if minutes and 1 <= minutes <= 45:
            target_sum += minutes
            mode = normalize_mode(item.get("completion_mode"), default_mode)
            tasks.append(
                MissionTask(
                    instruction=instruction or "Head outside and take a look around.",
                    target_minutes=minutes,
                    completion_mode=mode,
                )
            )

    # Task durations must be plausible for the requested total.
    effective_total = total if total in VALID_DURATIONS else request.duration_minutes
    if tasks:
        minimum = int(effective_total * 0.6)
        maximum = int(effective_total * 1.4)
        if target_sum < minimum or target_sum > maximum:
            issues.append(
                {
                    "field": "tasks.target_minutes",
                    "message": (
                        f"task durations add up to {target_sum} min but should be "
                        f"{minimum}-{maximum} min for a {effective_total} min mission"
                    ),
                }
            )
        for idx, task in enumerate(tasks, start=1):
            if task.target_minutes > effective_total:
                issues.append(
                    {
                        "field": f"tasks[{idx}].target_minutes",
                        "message": f"single task ({task.target_minutes} min) exceeds the whole mission",
                    }
                )

    # --- safety notes --------------------------------------------------------
    safety_notes = _as_str_list(raw.get("safety_notes"))
    safety_notes = [n[:200] for n in safety_notes][:6]
    if not safety_notes:
        issues.append(
            {"field": "safety_notes", "message": "must include at least one safety note"}
        )
    else:
        short = [i for i, n in enumerate(safety_notes, start=1) if len(n) < 5]
        for i in short:
            issues.append({"field": f"safety_notes[{i}]", "message": "safety note is too short"})

    # --- danger / suitability scan ------------------------------------------
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, title + " " + description, re.IGNORECASE):
            issues.append({"field": "title/description", "message": f"unsafe content: {reason}"})
    for idx, item in enumerate(tasks_raw, start=1):
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("instruction"))
        for pattern, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append({"field": f"tasks[{idx}].instruction", "message": f"unsafe content: {reason}"})
        for pattern, reason in INDOOR_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append({"field": f"tasks[{idx}].instruction", "message": f"not outdoors: {reason}"})

    if issues:
        return ValidationResult(issues=issues, warnings=warnings)

    # --- assemble ------------------------------------------------------------
    if len(tasks) > 5:
        tasks = tasks[:5]
    for i, task in enumerate(tasks, start=1):
        task.id = f"t{i}"

    mission = Mission(
        title=title,
        description=description,
        total_duration_minutes=effective_total,
        tasks=tasks,
        completion_mode=default_mode,
        safety_notes=safety_notes,
        activity=request.activity,
        energy=request.energy,
        difficulty=request.difficulty,
        warnings=warnings,
    )
    return ValidationResult(mission=mission, warnings=warnings)


def raise_if_invalid(result: ValidationResult) -> Mission:
    if not result.ok or result.mission is None:
        raise MissionValidationError(result.issues)
    return result.mission


# --- Bundled sample mission (always labelled as a sample) --------------------

SAMPLE_MISSION_PAYLOAD: dict = {
    "title": "Sample: Dawn-to-Dusk Sensory Loop",
    "description": (
        "A gentle sample mission you can run without any AI: step outside, let your "
        " senses lead, and finish with a short note about what you noticed."
    ),
    "total_duration_minutes": 30,
    "completion_mode": "manual",
    "tasks": [
        {
            "instruction": "Walk to the nearest patch of green and stand still for two minutes. "
            "Notice three sounds you would normally miss.",
            "target_minutes": 6,
            "completion_mode": "timer",
        },
        {
            "instruction": "Follow a route you have never taken before and photograph or "
            "sketch one texture you find interesting.",
            "target_minutes": 12,
            "completion_mode": "manual",
        },
        {
            "instruction": "Sit somewhere with a view for five minutes, then walk home "
            "and name one thing you would look at again tomorrow.",
            "target_minutes": 8,
            "completion_mode": "manual",
        },
    ],
    "safety_notes": [
        "Stay on public paths and respect private property and closures.",
        "Bring water and wear shoes suited to the ground underfoot.",
        "Cross roads at crossings and keep one ear free for traffic.",
    ],
}


def build_sample_mission(request: Optional[MissionRequest] = None) -> Mission:
    """The bundled sample mission. `source` is always 'sample' so the UI can
    label it unmistakably as NOT AI-generated."""
    request = request or MissionRequest(activity=ActivityType.explore_nature, duration_minutes=30)
    payload = json.loads(json.dumps(SAMPLE_MISSION_PAYLOAD))
    payload["total_duration_minutes"] = request.duration_minutes
    if request.duration_minutes == 15:
        payload["tasks"] = [
            payload["tasks"][0],
            {
                "instruction": "Pick one direction and walk until you spot three different "
                "colours of green.",
                "target_minutes": 5,
                "completion_mode": "manual",
            },
            {
                "instruction": "Finish with a slow lap of the block while your phone stays "
                "in your pocket.",
                "target_minutes": 4,
                "completion_mode": "manual",
            },
        ]
    elif request.duration_minutes == 60:
        payload["tasks"].append(
            {
                "instruction": "Find a bench, sit for fifteen minutes, and list five small "
                "details within arm's reach that you had never noticed.",
                "target_minutes": 20,
                "completion_mode": "timer",
            }
        )
    payload["energy"] = request.energy.value
    payload["difficulty"] = request.difficulty.value
    result = validate_mission(payload, request)
    mission = raise_if_invalid(result)
    mission.source = "sample"
    mission.provider = None
    mission.model = None
    return mission
