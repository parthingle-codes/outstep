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

from .archetypes import ArchetypeSpec, resolve_archetype
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

# --- Task quality: concreteness and distinctness ------------------------------
#
# The classic failure mode of an outdoor-mission model is padding a mission
# with rewordings of the same vague instruction ("walk and notice things").
# Two deterministic checks prevent it:
#
#   * concreteness - every task must carry at least one *concrete signal*
#     (a count, a comparison, a deliverable verb, a named object...), so
#     "notice your surroundings" is rejected but "count three red doors" passes
#   * distinctness - tasks are reduced to canonical action/object tokens and
#     compared pairwise; two tasks that are rewordings of one objective are
#     rejected with feedback naming both tasks

# Scaffolding words that never distinguish one objective from another.
TASK_STOPWORDS = frozenset(
    """
    a an the and or but if then than of to in on at for with from by as is are was
    were be been being am do does did done doing have has had having you your yours
    yourself yourselves it its itself this that these those there here i me my mine
    we our ours us they them their theirs he she him her hers him who whom whose
    what where when how why which while during after before around about into out
    up down off over under again also can could would should will shall may might
    must let lets now so very really just even well back way get got take taking
    spend spent time times min mins minutes minute second seconds head
    """.split()
)

# Ordered specific -> generic: the first group found decides the task's primary
# action, which is what the distinctness check compares.
ACTION_GROUP_PATTERNS: List[Tuple[str, str]] = [
    ("compare", r"\b(compare|versus|vs|match(ing)?|differ(ence|ent|s)?|similar(ity|ities)?|rank(ed|ing)?|sort(ed|ing)?|pair(ed|ing)? up)\b"),
    ("count", r"\b(count(ing|s|ed)?|tally(ing|s|ed)?|how many|enumerate)\b"),
    ("make", r"\b(draw|draws|drawing|sketch(es|ing)?|photograph(s|ed|ing)?|photo(s)?|snap(s|ped|ping)?|capture(s|d)?|writ(e|es|ing)|jot(s|ted|ting)?|note(s|d|ing)? down|record(s|ed|ing)?|list(s|ed|ing)?|name(s|d|ing)?|map(s|ped|ping)?|trace(s|d|ing)?|scribbl(e|es|ing)|log(s|ged|ging)?|recite(s|d|ing)?|spell(s|ed|ing)?|memoris(e|es|ing)|memoriz(e|es|ing)|add up|estimate(s|d)?|imagine|pretend)\b"),
    ("find", r"\b(find|finds|finding|search(es|ed|ing)?|hunt(s|ed|ing)?|locat(e|es|ed|ing)|seek(ing)?|spot(s|ted|ting)?|pick(s|ed|ing)? out|choose|chose|select(s|ed|ing)?|collect(s|ed|ing)?|gather(s|ed|ing)?|checklist|bingo)\b"),
    ("still", r"\b(sit(s|ting)?|stand(s|ing)?|stay|stays|staying|settl(e|es|ing)|pause(s|d|ing)?|stop(s|ping)?|linger(s|ing)?|perch(es|ed|ing)?|freeze|hold still|balance(s|d|ing)?)\b"),
    ("listen", r"\b(listen(s|ing)?|hear(s|d|ing)?|sound(s)?|soundscape|noise(s)?)\b"),
    ("observe", r"\b(notice(s|d|ing)?|observ(e|es|ed|ing)|look(s|ed|ing)?|watch(es|ed|ing)?|gaz(e|es|ed|ing)|admire(s|d|ing)?|inspect(s|ed|ing)?|stud(y|ies|ied)|peek(s|ed|ing)?|view(s|ed|ing)?|see|seeing)\b"),
    ("relax", r"\b(relax(es|ed|ing)?|breath(e|es|ed|ing)|breathing|breath|calm(s|ed|ing)?|unwind(s|ing)?|chill(s|ed|ing)?|de-stress(es|ed|ing)?|meditat(e|es|ed|ing)|mindful(ness)?|unplug(s|ged|ging)?)\b"),
    ("move", r"\b(walk(s|ed|ing)?|stroll(s|ed|ing)?|wander(s|ed|ing)?|roam(s|ed|ing)?|hike(s|d|ing)?|march(es|ed|ing)?|jog(s|ged|ging)?|run(s|ning)?|cycl(e|es|ed|ing)|rid(e|es|ing)|loop(s|ed|ing)?|lap(s|ped|ping)?|route(s|d)?|strid(e|es|ing)|ambl(e|es|ed|ing)|saunter(s|ed|ing)?|meander(s|ed|ing)?|drift(s|ed|ing)?|danc(e|es|ed|ing)|climb(s|ed|ing)?|skip(s|ped|ping|ing)?|travell?(s|ed|ing)|walkabout)\b"),
]

# Words that make a token count as the same objective across rewordings
# ("walk" and "stroll" collapse to one token, as do "notice" and "observe").
TOKEN_CANONICALS: dict = {}
for _group, _synonyms in [
    ("compare", ["compare", "versus", "match", "matching", "differ", "difference", "different", "distinct", "similar", "similarities", "rank", "sort"]),
    ("count", ["count", "counting", "tally", "tallying", "enumerate", "many"]),
    ("make", ["draw", "drawing", "sketch", "sketching", "photograph", "photo", "snap", "capture", "write", "writing", "jot", "note", "record", "list", "name", "naming", "map", "mapping", "trace", "tracing", "scribble", "log", "recite", "spell", "memorize", "memorise"]),
    ("find", ["find", "finding", "search", "searching", "hunt", "hunting", "locate", "seek", "spot", "spotting", "pick", "choose", "select", "collect", "gather"]),
    ("still", ["sit", "sitting", "stand", "standing", "stay", "staying", "settle", "pause", "stop", "linger", "perch", "freeze", "balance"]),
    ("listen", ["listen", "listening", "hear", "hearing", "sound", "sounds", "soundscape", "noise"]),
    ("observe", ["notice", "noticing", "observe", "observing", "look", "looking", "watch", "watching", "gaze", "admire", "inspect", "study", "peek", "view", "see", "seeing"]),
    ("relax", ["relax", "relaxing", "breathe", "breathing", "breath", "calm", "unwind", "chill", "meditate", "mindful", "unplug"]),
    ("move", ["walk", "walking", "stroll", "strolling", "wander", "roam", "hike", "march", "jog", "run", "running", "cycle", "cycling", "ride", "loop", "lap", "route", "stride", "amble", "saunter", "meander", "drift", "dance", "climb", "skip", "travelling", "traveling"]),
    ("colour", ["colour", "colours", "color", "colors"]),
]:
    for _syn in _synonyms:
        TOKEN_CANONICALS[_syn] = _group

# Generic actions: the same generic action twice in one mission is padding,
# even when the objects differ, unless both tasks are clearly concrete.
GENERIC_ACTION_GROUPS = frozenset({"move", "observe", "listen", "relax", "still"})

# A task is concrete when its instruction carries at least one of these signals:
# a count, a comparison/angle, a deliverable verb, a named object, or a real
# destination. Tasks with none of them are the "walk and notice" filler.
CONCRETE_SIGNALS: List[str] = [
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\b",
    r"\b(different|unique|compare|versus|vs|fewest|most|least|oldest|newest|largest|smallest|loudest|quietest|brightest|darkest|weirdest|strangest|oddest|fanciest|highest|lowest|longest|shortest|heaviest|biggest|tiniest|first|last|only|nearest|closest|furthest|farthest|new|weirdest)\b",
    r"\b(until|at least|at most|no more than|no fewer than|no less than|each|every)\b",
    r"\b(colou?rs?|textures?|shapes?|signs?|letters?|numbers?|doors?|doorways?|gates?|windows?|benches|bench|trees?|leaves|leaf|branches|bark|birds?|clouds?|shadows?|reflections?|footprints?|bricks?|graffiti|murals?|posters?|plaques?|mosaics?|tiles?|steps?|stairs|handrails?|railings?|walls?|roofs?|chimneys?|gutters?|drains?|smells?|scents?|breezes?|puddles?|cracks?|moss|fungi|mushrooms?|feathers?|shells?|stones?|pebbles?|twigs?|petals?|flowers?|weeds?|plants?|insects?|ants?|bees?|butterflies?|spiders?|webs?|squirrels?|pigeons?|ducks?|runners?|cyclists?|dog walkers?|passersby|strangers?|people|shops?|shopfronts?|postboxes?|letterboxes?|bins?|statues?|monuments?|fountains?|bridges?|arches?|kiosks?|lamp posts?|street names?|house numbers?|parking meters?|bollards?)\b",
]

# Fit checks: the mission must respect what the user asked for.
EFFORT_PATTERN = r"\b(brisk|jog|jogging|run|running|sprint|sprinting|stair|stairs|hill|hills|uphill|ramp|ramps|cycl(e|es|ed|ing)|bike|danc(e|es|ed|ing)|skipping|skip rope|marching|march|sweat|sweating|climb|climbing|push-?ups?|squats?|lunges?|burpees?|star jumps?|strides?|laps?|fitness|workout|intervals?|pace)\b|\d+(\.\d+)?\s?(km|kilometre|kilometer|mile|miles|steps)\b"
VIGOROUS_PATTERN = r"\b(sprint|sprinting|jog|jogging|run|running|vigorous|high-intensity|hiit|burpees?|racing|race|as fast as you can)\b"
MOVEMENT_PATTERN = r"\b(walks?|walking|stroll|strolling|wander|roam|hike|hiking|march|jog|jogging|runs?|running|cycl(e|es|ed|ing)|rides?|riding|loop|loops|lap|laps|route|routes|strides?|amble|saunter|meander|dance|climbing|climb|skipping|traveling|travelling|drift)\b|\d+(\.\d+)?\s?(km|kilometre|kilometer|mile|miles|steps)\b"
URGENCY_PATTERN = r"\b(race|racing|rush|rushing|hurry|hurrying|as fast as you can|beat your|personal best|no stopping|speed up|sprint|sprinting)\b"
CHALLENGE_PATTERN = r"\b(brisk|hills?|stair|stairs|uphill|ramp|ramps|faster|quick|quickly|pace|challenge|challenging|push|pushing|stretch|stretched|extra|longer|further|farther|sweat|jog|jogging|runs?|running|sprint|sprinting|climb|climbing|loops?|laps?|circuit|intervals?|double|twice|three times)\b|\d+(\.\d+)?\s?(km|kilometre|kilometer|mile|miles|steps)\b"

# Titles that are pure filler; a title must say something about *this* mission.
GENERIC_TITLE_PATTERNS: List[str] = [
    r"^(outdoor |nature |outdoors )?(adventure|mission|explore|exploration|walk|challenge|quest|journey|experience)( awaits| time| is here| is calling)?[!.]?$",
    r"^get outside[!.]?$",
    r"^mission (one|1)[!.]?$",
]

DUPLICATE_SIMILARITY_THRESHOLD = 0.45

SUM_WINDOW = (0.8, 1.2)  # task minutes must add up to 80-120% of the request


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


# --- Task quality helpers -----------------------------------------------------

def task_action(instruction: str) -> str:
    """The task's primary action group (specific actions win over generic ones)."""
    text = instruction.lower()
    for group, pattern in ACTION_GROUP_PATTERNS:
        if re.search(pattern, text):
            return group
    return "other"


def task_is_concrete(instruction: str) -> bool:
    """True when the instruction names a concrete objective, not vague filler."""
    text = instruction.lower()
    return any(re.search(pattern, text) for pattern in CONCRETE_SIGNALS)


def _canonical_token(word: str) -> str:
    base = word
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        base = word[:-1]
    return TOKEN_CANONICALS.get(word) or TOKEN_CANONICALS.get(base) or base


def canonical_tokens(instruction: str) -> set:
    """Content tokens of a task, with synonyms collapsed so rewordings match.

    "Walk through the park and notice three leaf shapes" and "stroll through
    the neighbourhood and observe three shopfronts" both reduce to
    {move, observe, three, compare, ...}, making their similarity obvious.
    """
    tokens = set()
    for word in re.findall(r"[a-z0-9']+", instruction.lower()):
        word = word.strip("'")
        if not word or word in TASK_STOPWORDS:
            continue
        tokens.add(_canonical_token(word))
    return tokens


def task_quality_issues(entries: List[Tuple[int, str]]) -> List[dict]:
    """Concreteness + distinctness issues for the mission's tasks.

    `entries` is a list of (1-based task index, instruction) pairs.
    """
    issues: List[dict] = []
    actions: List[str] = []
    tokens: List[set] = []
    concrete: List[bool] = []

    for idx, text in entries:
        actions.append(task_action(text))
        tokens.append(canonical_tokens(text))
        is_concrete = task_is_concrete(text)
        concrete.append(is_concrete)
        if not is_concrete:
            issues.append(
                {
                    "field": f"tasks[{idx}].instruction",
                    "message": (
                        "task is too generic - give it ONE concrete objective (what exactly "
                        "to find, count, compare, sketch or map). Walking, noticing "
                        "surroundings, listening to sounds and relaxing are not objectives."
                    ),
                }
            )

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            idx_i, idx_j = entries[i][0], entries[j][0]
            intersection = tokens[i] & tokens[j]
            union = tokens[i] | tokens[j]
            similarity = len(intersection) / len(union) if union else 0.0
            same_action = actions[i] == actions[j] and actions[i] != "other"
            both_weak = (not concrete[i]) or (not concrete[j])

            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD and (
                same_action or len(intersection) >= 3
            ):
                issues.append(
                    {
                        "field": f"tasks[{idx_i}]/tasks[{idx_j}]",
                        "message": (
                            "these two tasks are rewordings of the same objective - give "
                            "them different goals, actions or targets"
                        ),
                    }
                )
            elif (
                same_action
                and both_weak
                and actions[i] in GENERIC_ACTION_GROUPS
            ):
                issues.append(
                    {
                        "field": f"tasks[{idx_i}]/tasks[{idx_j}]",
                        "message": (
                            "both tasks are the same generic "
                            f"'{actions[i]}' instruction - make one of them do "
                            "something concrete and different"
                        ),
                    }
                )
    return issues


def request_fit_issues(entries: List[Tuple[int, str]], request: MissionRequest) -> List[dict]:
    """Issues raised when the tasks ignore the requested activity/energy/difficulty."""
    issues: List[dict] = []
    if not entries:
        return issues

    def any_match(pattern: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for _, text in entries)

    if request.energy is EnergyLevel.high and not any_match(EFFORT_PATTERN):
        issues.append(
            {
                "field": "tasks",
                "message": (
                    "energy level is 'high' but no task asks for real physical effort - "
                    "add brisk movement, stairs, hills or distance to at least one task"
                ),
            }
        )

    if request.energy is EnergyLevel.low:
        for idx, text in entries:
            match = re.search(VIGOROUS_PATTERN, text, re.IGNORECASE)
            if match:
                issues.append(
                    {
                        "field": f"tasks[{idx}].instruction",
                        "message": (
                            f"energy level is 'low' but this task asks for vigorous effort "
                            f"('{match.group(0)}') - dial it down to a gentle pace"
                        ),
                    }
                )

    if request.activity is ActivityType.move and not any_match(MOVEMENT_PATTERN):
        issues.append(
            {
                "field": "tasks",
                "message": (
                    "activity is 'move' but no task gets the body moving - at least one "
                    "task should involve walking, stairs, cycling or similar"
                ),
            }
        )

    if request.difficulty is Difficulty.chill:
        for idx, text in entries:
            match = re.search(URGENCY_PATTERN, text, re.IGNORECASE)
            if match:
                issues.append(
                    {
                        "field": f"tasks[{idx}].instruction",
                        "message": (
                            f"difficulty is 'chill' but this task pushes the user "
                            f"('{match.group(0)}') - remove the rush or competition"
                        ),
                    }
                )

    if request.difficulty is Difficulty.push and not any_match(CHALLENGE_PATTERN):
        issues.append(
            {
                "field": "tasks",
                "message": (
                    "difficulty is 'push' but nothing stretches the user - add a brisk "
                    "pace, a hill, stairs, a longer loop or extra distance to one task"
                ),
            }
        )

    return issues


def title_issues(title: str) -> List[dict]:
    """Reject pure-filler titles like 'Adventure Awaits'."""
    lowered = title.strip().lower()
    for pattern in GENERIC_TITLE_PATTERNS:
        if re.match(pattern, lowered):
            return [
                {
                    "field": "title",
                    "message": (
                        "title is too generic - make it specific to this mission's "
                        "archetype and objective"
                    ),
                }
            ]
    return []


# --- The validator -----------------------------------------------------------

def validate_mission(
    raw: Any,
    request: MissionRequest,
    archetype: Optional[ArchetypeSpec] = None,
) -> ValidationResult:
    """Validate raw model output against `request`.

    Returns a `ValidationResult`; `result.mission` is set only when the payload
    is safe and usable. Non-fatal normalizations are recorded in `warnings`.
    `archetype` is the style the server selected for this generation; when it
    is omitted, a valid archetype echoed by the model (or a fresh random pick)
    is used instead.
    """
    issues: List[dict] = []
    warnings: List[str] = []

    if not isinstance(raw, dict):
        issues.append({"field": "root", "message": "model output must be a JSON object"})
        return ValidationResult(issues=issues)

    # --- archetype -------------------------------------------------------------
    archetype_spec = resolve_archetype(raw, request, archetype)

    # --- title / description -------------------------------------------------
    title = _clean_text(raw.get("title"))
    if len(title) < 3:
        issues.append({"field": "title", "message": "title must be at least 3 characters"})
    elif len(title) > 80:
        title = title[:80]
        warnings.append("title was shortened to 80 characters")
    issues.extend(title_issues(title))

    description = _clean_text(raw.get("description"))
    if len(description) < 10:
        issues.append({"field": "description", "message": "description must be at least 10 characters"})
    elif len(description) > 500:
        description = description[:500]
        warnings.append("description was shortened to 500 characters")

    # --- objective -------------------------------------------------------------
    objective = _clean_text(raw.get("objective"))
    if len(objective) < 15:
        issues.append(
            {
                "field": "objective",
                "message": (
                    "objective must be one clear sentence (at least 15 characters) "
                    "stating what the person will have seen, found or done by the end"
                ),
            }
        )
    elif len(objective) > 300:
        objective = objective[:300]
        warnings.append("objective was shortened to 300 characters")

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
    task_entries: List[Tuple[int, str]] = []  # (index, instruction) for quality checks
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
        if instruction:
            task_entries.append((idx, instruction))

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

    # Task durations must add up consistently to the requested total.
    effective_total = total if total in VALID_DURATIONS else request.duration_minutes
    if tasks:
        minimum = int(effective_total * SUM_WINDOW[0])
        maximum = int(effective_total * SUM_WINDOW[1])
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

    # --- task quality: concrete objectives, all different ---------------------
    issues.extend(task_quality_issues(task_entries))

    # --- the mission must respect what the user asked for --------------------
    issues.extend(request_fit_issues(task_entries, request))

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
        objective=objective,
        total_duration_minutes=effective_total,
        tasks=tasks,
        completion_mode=default_mode,
        safety_notes=safety_notes,
        activity=request.activity,
        energy=request.energy,
        difficulty=request.difficulty,
        archetype=archetype_spec.id,
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
    "objective": (
        "Come home able to name three small things on your usual patch that you had "
        "never clocked before."
    ),
    "archetype": "micro_explorer",
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
            "instruction": "Take a brisk walk along a route you have never taken before and "
            "photograph or sketch one texture you find interesting.",
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
                "instruction": "Finish with a slow lap of the block, counting the windows "
                "you pass with your phone in your pocket.",
                "target_minutes": 4,
                "completion_mode": "manual",
            },
        ]
    elif request.duration_minutes == 60:
        payload["tasks"].append(
            {
                "instruction": "Find a bench, sit for twenty-four minutes, and list five small "
                "details within arm's reach that you had never noticed.",
                "target_minutes": 24,
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
