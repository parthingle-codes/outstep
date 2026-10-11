"""Mission archetypes: the creative style a generation is built around.

The single biggest quality lever in OutStep is *variety with intent*. Every
generation picks one archetype (Visual Detective, Nature Bingo, ...) and the
whole mission - title, hook, objective, tasks - is written in that style.
The archetype is selected on the server, injected into the prompt, and stamped
onto the validated mission; the model is asked to echo it but never decides it.

Selection rules (deterministic given an rng, testable via `rng=`):

  * archetypes that suit the requested activity score higher (+2)
  * archetypes that suit the requested energy level score higher (+1)
  * "intense" archetypes (e.g. Movement Quest) are never chosen for low energy
  * among the best-scoring archetypes one is drawn at random, so repeated
    generations of the same request still surprise the user
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .schemas import ActivityType, EnergyLevel, MissionArchetype, MissionRequest

ALL_ACTIVITIES: Tuple[ActivityType, ...] = tuple(ActivityType)
ALL_ENERGIES: Tuple[EnergyLevel, ...] = tuple(EnergyLevel)


@dataclass(frozen=True)
class ArchetypeSpec:
    """One creative style. `brief` is sent to the model as the style guide."""

    id: MissionArchetype
    label: str
    tagline: str  # short, UI-friendly description of the flavour
    brief: str  # instructions telling the model what this style looks like
    activities: Tuple[ActivityType, ...]  # activities this style suits best
    energies: Tuple[EnergyLevel, ...]  # energy levels it suits best
    intense: bool = False  # never chosen when the user asks for low energy


ALL_ARCHETYPES: Tuple[ArchetypeSpec, ...] = (
    ArchetypeSpec(
        id=MissionArchetype.visual_detective,
        label="Visual Detective",
        tagline="Hunt for visual clues other people walk past.",
        brief=(
            "The user is a detective and the street is the case file. Tasks chase visual "
            "evidence: read signs and plaques, find the oldest or newest house number, "
            "spot worn-away lettering, notice what colour doors repeat on the street. "
            "Every task should end with a specific clue found, counted or sketched."
        ),
        activities=ALL_ACTIVITIES,
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.nature_bingo,
        label="Nature Bingo",
        tagline="Tick off a checklist of small natural finds.",
        brief=(
            "Turn the outdoors into a bingo card. Tasks collect specific natural finds - "
            "three different leaf shapes, something soft, something mossy, a bird, a seed "
            "pod, three shades of green - and each task is one row of the card to tick off."
        ),
        activities=(ActivityType.explore_nature, ActivityType.observe),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.urban_archaeologist,
        label="Urban Archaeologist",
        tagline="Read the layers of history in ordinary streets.",
        brief=(
            "The user excavates a normal street with their eyes. Tasks read the layers of "
            "a place: dated plaques, old versus new brick, worn steps, faded painted signs, "
            "the oldest door they can find, traces of what used to be there. Concrete "
            "targets only - a date, a name, a material, a thing that is older than them."
        ),
        activities=(ActivityType.observe, ActivityType.clear_my_head, ActivityType.move),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.colour_quest,
        label="Colour Quest",
        tagline="Chase a palette through the neighbourhood.",
        brief=(
            "Colour is the objective. Tasks hunt for specific colours or build a palette: "
            "one thing for every colour of a rainbow, the faded reddest wall, five things "
            "that are almost-but-not-quite the same colour, the brightest flower on the "
            "block. Always name the colour or the count."
        ),
        activities=(ActivityType.explore_nature, ActivityType.observe, ActivityType.clear_my_head),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.pattern_breaker,
        label="Pattern Breaker",
        tagline="Find patterns, then find what breaks them.",
        brief=(
            "Spot repetitions and the odd one out. Tasks look for a run of identical "
            "things (doors, tiles, bollards, windows) and the single element that breaks "
            "the pattern, or a rhythm the user can break in their own route. Always name "
            "the pattern and the breaker."
        ),
        activities=(ActivityType.observe, ActivityType.clear_my_head, ActivityType.move),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.sound_mapper,
        label="Sound Mapper",
        tagline="Map the soundscape you usually filter out.",
        brief=(
            "The user maps sound like a cartographer. Tasks categorise what they hear by "
            "direction or texture (natural, mechanical, human), find the loudest and "
            "quietest corners, count passing sounds, or trace one sound to its source. "
            "Sound must be counted, sorted or located - never just 'listen'."
        ),
        activities=(ActivityType.clear_my_head, ActivityType.observe, ActivityType.explore_nature),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.route_quest,
        label="Route Quest",
        tagline="A route with self-made rules.",
        brief=(
            "The journey is the mission. Tasks invent playful route constraints: only "
            "left turns, never take the same street twice, reach a landmark and return "
            "another way, follow the shadiest line. Each task states the constraint and "
            "the landmark so 'done' is unambiguous."
        ),
        activities=(ActivityType.move, ActivityType.explore_nature, ActivityType.clear_my_head),
        energies=(EnergyLevel.moderate, EnergyLevel.high),
    ),
    ArchetypeSpec(
        id=MissionArchetype.micro_explorer,
        label="Micro-Explorer",
        tagline="A whole world at fingertips' range.",
        brief=(
            "The user shrinks their world to arm's reach. Tasks get physically close to "
            "things: sketch the strangest texture within one metre, count the tiny things "
            "growing out of a wall, compare two leaves at macro range. Tiny targets, "
            "concrete results."
        ),
        activities=(ActivityType.explore_nature, ActivityType.observe, ActivityType.clear_my_head),
        energies=ALL_ENERGIES,
    ),
    ArchetypeSpec(
        id=MissionArchetype.movement_quest,
        label="Movement Quest",
        tagline="The body is the way through the mission.",
        brief=(
            "Movement is woven into discovery, never a fitness drill. Tasks use the body "
            "to reach or reveal things: take the stairs to a viewpoint, walk briskly "
            "between two landmarks, balance along a line, add one loop to the route. "
            "Always pair the effort with something to look at or find on the way."
        ),
        activities=(ActivityType.move, ActivityType.explore_nature),
        energies=(EnergyLevel.moderate, EnergyLevel.high),
        intense=True,
    ),
)

ARCHETYPE_BY_ID = {spec.id: spec for spec in ALL_ARCHETYPES}

ARCHETYPE_IDS: Tuple[str, ...] = tuple(spec.id.value for spec in ALL_ARCHETYPES)


def _normalize_archetype_id(value: Any) -> Optional[str]:
    """Accept enum members, ids, labels and sloppy variants ("Visual Detective")."""
    if isinstance(value, MissionArchetype):
        return value.value
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def get_archetype(value: Any) -> Optional[ArchetypeSpec]:
    """Look up a spec from an id/label/enum, or None if unknown."""
    normalized = _normalize_archetype_id(value)
    if normalized is None:
        return None
    for spec in ALL_ARCHETYPES:
        if spec.id.value == normalized:
            return spec
    for spec in ALL_ARCHETYPES:  # label lookup, e.g. "Visual Detective"
        if re.sub(r"[\s\-]+", "_", spec.label.lower()) == normalized:
            return spec
    return None


def score_archetype(spec: ArchetypeSpec, request: MissionRequest) -> int:
    """How well a style fits the request. Higher is better."""
    score = 0
    if request.activity in spec.activities:
        score += 2
    if request.energy in spec.energies:
        score += 1
    return score


def eligible_archetypes(request: MissionRequest) -> List[ArchetypeSpec]:
    """Archetypes that may be chosen for this request, best-scoring first."""
    candidates = [s for s in ALL_ARCHETYPES if not (s.intense and request.energy == EnergyLevel.low)]
    best = max(score_archetype(s, request) for s in candidates)
    return [s for s in candidates if score_archetype(s, request) == best]


def select_archetype(
    request: MissionRequest,
    *,
    rng: Optional[random.Random] = None,
) -> ArchetypeSpec:
    """Pick one archetype for this generation. Reproducible with a seeded rng."""
    candidates = eligible_archetypes(request)
    chooser = rng.choice if rng is not None else random.choice
    return chooser(candidates)


def resolve_archetype(
    raw: Any,
    request: MissionRequest,
    archetype: Optional[ArchetypeSpec] = None,
    *,
    rng: Optional[random.Random] = None,
) -> ArchetypeSpec:
    """Decide the archetype for one validation run.

    Precedence: explicit selection (the server chose it for this generation) >
    a valid archetype echoed by the model > a fresh random selection.
    """
    if archetype is not None:
        return archetype
    if isinstance(raw, dict):
        declared = get_archetype(raw.get("archetype"))
        if declared is not None:
            return declared
    return select_archetype(request, rng=rng)
