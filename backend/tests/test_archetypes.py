"""Tests for archetype selection: the creative style behind every generation."""

import random

from backend.archetypes import (
    ALL_ARCHETYPES,
    ARCHETYPE_IDS,
    eligible_archetypes,
    get_archetype,
    resolve_archetype,
    score_archetype,
    select_archetype,
)
from backend.schemas import ActivityType, EnergyLevel, MissionArchetype, MissionRequest


def request_for(activity="explore_nature", duration=30, energy="moderate", difficulty="steady"):
    return MissionRequest(
        activity=activity,
        duration_minutes=duration,
        energy=energy,
        difficulty=difficulty,
    )


def test_all_nine_archetypes_are_defined():
    assert len(ALL_ARCHETYPES) == 9
    assert {spec.id for spec in ALL_ARCHETYPES} == set(MissionArchetype)
    assert set(ARCHETYPE_IDS) == {member.value for member in MissionArchetype}
    # Labels and ids must be unique so the UI never shows duplicates.
    labels = [spec.label for spec in ALL_ARCHETYPES]
    assert len(set(labels)) == len(labels)
    assert len(set(ARCHETYPE_IDS)) == len(ARCHETYPE_IDS)


def test_every_archetype_has_a_brief_and_a_tagline():
    for spec in ALL_ARCHETYPES:
        assert len(spec.brief) > 80, f"{spec.id} needs a real brief for the model"
        assert spec.tagline and spec.label


def test_get_archetype_accepts_ids_labels_and_sloppy_variants():
    assert get_archetype("visual_detective").id is MissionArchetype.visual_detective
    assert get_archetype("Visual Detective").id is MissionArchetype.visual_detective
    assert get_archetype("Colour-Quest").id is MissionArchetype.colour_quest
    assert get_archetype(MissionArchetype.sound_mapper).id is MissionArchetype.sound_mapper
    assert get_archetype("banana") is None
    assert get_archetype(None) is None
    assert get_archetype(42) is None


def test_selection_is_reproducible_with_a_seeded_rng():
    request = request_for("observe")
    first = [select_archetype(request, rng=random.Random(7)).id for _ in range(6)]
    second = [select_archetype(request, rng=random.Random(7)).id for _ in range(6)]
    assert first == second


def test_selection_is_stable_for_a_request():
    """Eligibility only depends on the request, so scoring stays deterministic."""
    request = request_for("move", energy="high")
    best = max(score_archetype(spec, request) for spec in ALL_ARCHETYPES)
    for spec in eligible_archetypes(request):
        assert score_archetype(spec, request) == best


def test_every_archetype_can_be_selected_for_some_request():
    reachable = set()
    for activity in ActivityType:
        for energy in EnergyLevel:
            request = request_for(activity, energy=energy)
            for seed in range(150):
                reachable.add(select_archetype(request, rng=random.Random(seed)).id)
    assert reachable == set(MissionArchetype)


def test_low_energy_never_selects_an_intense_archetype():
    for activity in ActivityType:
        request = request_for(activity, energy="low")
        for seed in range(60):
            chosen = select_archetype(request, rng=random.Random(seed))
            assert not chosen.intense, f"{chosen.id} must not be offered at low energy"
            assert chosen is not get_archetype("movement_quest")


def test_activity_and_energy_raise_an_archetypes_score():
    spec = get_archetype("movement_quest")
    assert score_archetype(spec, request_for("move", energy="high")) > score_archetype(
        spec, request_for("observe", energy="low")
    )


def test_resolve_archetype_precedence():
    request = request_for("observe")
    explicit = get_archetype("sound_mapper")

    # 1. explicit selection wins over anything the model echoed
    resolved = resolve_archetype({"archetype": "colour_quest"}, request, archetype=explicit)
    assert resolved is explicit

    # 2. a valid echo by the model is used when nothing was pre-selected
    resolved = resolve_archetype({"archetype": "colour_quest"}, request)
    assert resolved.id is MissionArchetype.colour_quest

    # 3. invalid or missing echoes fall back to a fresh selection
    assert resolve_archetype({"archetype": "banana"}, request, rng=random.Random(3))
    assert resolve_archetype({}, request, rng=random.Random(3))
    assert resolve_archetype("not a dict", request, rng=random.Random(3))


def test_repeated_generations_of_one_request_vary():
    """Same request, many generations: the user should not see the same style twice in a row."""
    request = request_for("explore_nature", duration=30)
    picks = [select_archetype(request, rng=random.Random(seed)).id for seed in range(40)]
    assert len(set(picks)) > 1, "archetype selection must offer variety across generations"
