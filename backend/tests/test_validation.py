"""Tests for deterministic mission validation and safety checks."""

import pytest

from backend.archetypes import get_archetype
from backend.schemas import ActivityType, CompletionMode, MissionArchetype, MissionRequest
from backend.validation import (
    MissionValidationError,
    build_sample_mission,
    extract_json,
    raise_if_invalid,
    validate_mission,
)


def test_valid_payload_passes(request_30, good_payload):
    result = validate_mission(good_payload, request_30)
    assert result.ok, result.issues
    mission = result.mission
    assert mission.total_duration_minutes == 30
    assert len(mission.tasks) == 4
    assert [t.id for t in mission.tasks] == ["t1", "t2", "t3", "t4"]
    assert mission.tasks[0].completion_mode is CompletionMode.timer
    assert mission.safety_notes


def test_task_count_bounds(request_30, good_payload):
    too_few = dict(good_payload, tasks=good_payload["tasks"][:2])
    result = validate_mission(too_few, request_30)
    assert not result.ok
    assert any("3-5" in i["message"] for i in result.issues)

    too_many = dict(
        good_payload, tasks=good_payload["tasks"] + good_payload["tasks"][:2]
    )
    result = validate_mission(too_many, request_30)
    assert not result.ok
    assert any("3-5" in i["message"] for i in result.issues)


def test_task_duration_sum_must_match_requested_total(request_30, good_payload):
    payload = dict(good_payload, tasks=[
        dict(t, target_minutes=1) for t in good_payload["tasks"]
    ])
    result = validate_mission(payload, request_30)
    assert not result.ok
    assert any("task durations add up" in i["message"] for i in result.issues)


def test_single_task_cannot_exceed_mission(request_30, good_payload):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["target_minutes"] = 45  # > 30 min mission, and sum is now too big
    tasks[1]["target_minutes"] = 1
    tasks[2]["target_minutes"] = 1
    tasks[3]["target_minutes"] = 1
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert not result.ok
    assert any("exceeds the whole mission" in i["message"] for i in result.issues)


def test_target_minutes_out_of_range(request_30, good_payload):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["target_minutes"] = 60
    tasks[1]["target_minutes"] = 0
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert not result.ok
    assert sum("between 1 and 45" in i["message"] for i in result.issues) == 2


def test_safety_notes_required(request_30, good_payload):
    payload = dict(good_payload, safety_notes=[])
    result = validate_mission(payload, request_30)
    assert not result.ok
    assert any(i["field"] == "safety_notes" for i in result.issues)


@pytest.mark.parametrize("bad_instruction", [
    "Trespass across the old depot to save a few minutes.",
    "Walk along the highway shoulder and wave at cars.",
    "Climb the cliff edge for a better view of the bay.",
    "Head indoors and watch a video about nature instead.",
    "Enter an abandoned building and explore the halls.",
    "Cross the railway tracks to reach the other side.",
])
def test_dangerous_or_indoor_tasks_rejected(request_30, good_payload, bad_instruction):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[1]["instruction"] = bad_instruction
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert not result.ok
    assert any(
        i["field"].startswith("tasks[2]") for i in result.issues
    ), result.issues


def test_title_and_description_bounds(request_30, good_payload):
    result = validate_mission(dict(good_payload, title="Hi"), request_30)
    assert not result.ok
    result = validate_mission(dict(good_payload, description="short"), request_30)
    assert not result.ok


def test_total_duration_mismatch_is_normalised_with_warning(request_30, good_payload):
    payload = dict(good_payload, total_duration_minutes=60)  # model ignored the request
    result = validate_mission(payload, request_30)
    assert result.ok, result.issues
    assert result.mission.total_duration_minutes == 30
    assert any("requested 30" in w for w in result.mission.warnings)


def test_total_duration_must_be_one_of_allowed(request_30, good_payload):
    result = validate_mission(dict(good_payload, total_duration_minutes=45), request_30)
    # 45 is not an allowed duration at all -> issue (even though 30 was requested)
    assert any(i["field"] == "total_duration_minutes" for i in result.issues)


def test_string_durations_are_coerced(request_30, good_payload):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["target_minutes"] = "8 minutes"
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert result.ok, result.issues
    assert result.mission.tasks[0].target_minutes == 8


def test_completion_mode_synonyms(request_30, good_payload):
    payload = dict(good_payload, completion_mode="simple timer")
    result = validate_mission(payload, request_30)
    assert result.ok, result.issues
    assert result.mission.completion_mode is CompletionMode.timer


def test_non_object_output_is_rejected(request_30):
    result = validate_mission(["not", "a", "mission"], request_30)
    assert not result.ok


def test_raise_if_invalid_raises(request_30, good_payload):
    payload = dict(good_payload, safety_notes=[])
    with pytest.raises(MissionValidationError) as exc:
        raise_if_invalid(validate_mission(payload, request_30))
    assert exc.value.issues


# --- Mission quality: objective, archetype, concreteness, distinctness --------

def test_valid_payload_carries_objective_and_archetype(request_30, good_payload):
    result = validate_mission(good_payload, request_30)
    assert result.ok, result.issues
    mission = result.mission
    assert mission.objective == good_payload["objective"]
    assert mission.archetype is MissionArchetype.nature_bingo


def test_objective_is_required(request_30, good_payload):
    payload = dict(good_payload)
    payload.pop("objective")
    result = validate_mission(payload, request_30)
    assert not result.ok
    assert any(i["field"] == "objective" for i in result.issues)


def test_objective_must_be_a_real_sentence(request_30, good_payload):
    result = validate_mission(dict(good_payload, objective="Explore!"), request_30)
    assert not result.ok
    assert any(i["field"] == "objective" for i in result.issues)


def test_archetype_falls_back_to_selection_when_missing_or_unknown(request_30, good_payload):
    payload = dict(good_payload)
    payload.pop("archetype")
    result = validate_mission(payload, request_30)
    assert result.ok, result.issues
    assert result.mission.archetype in MissionArchetype

    result = validate_mission(dict(good_payload, archetype="banana"), request_30)
    assert result.ok, result.issues
    assert result.mission.archetype in MissionArchetype


def test_explicit_archetype_overrides_model_echo(request_30, good_payload):
    spec = get_archetype("urban_archaeologist")
    result = validate_mission(good_payload, request_30, archetype=spec)
    assert result.ok, result.issues
    assert result.mission.archetype is MissionArchetype.urban_archaeologist


def test_generic_tasks_are_rejected(request_30):
    """The classic failure: a mission padded with walk/notice/listen/relax filler."""
    payload = {
        "title": "Neighbourhood Wind-Down",
        "description": "A gentle loop around your local streets with time to breathe.",
        "objective": "Finish the walk feeling calmer than when you started out.",
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
    result = validate_mission(payload, request_30)
    assert not result.ok
    generic = [i for i in result.issues if "concrete objective" in i["message"]]
    assert len(generic) == 4, result.issues


def test_reworded_duplicate_tasks_are_rejected(request_30, good_payload):
    """Two walk-and-observe variants are the same objective twice."""
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["instruction"] = (
        "Walk through the green park and notice three different trees near the path."
    )
    tasks[1]["instruction"] = (
        "Stroll through the neighbourhood park and observe three different shopfronts "
        "near the corner."
    )
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert not result.ok
    assert any("rewordings" in i["message"] for i in result.issues), result.issues


def test_same_action_with_same_target_is_a_rewording(request_30, good_payload):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["instruction"] = "Find three doorways with painted numbers on this street."
    tasks[1]["instruction"] = "Find three windows with painted numbers on that street."
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert not result.ok
    assert any("rewordings" in i["message"] for i in result.issues), result.issues


def test_different_concrete_objectives_pass(request_30, good_payload):
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["instruction"] = "Sketch the strangest texture you can reach within one metre."
    result = validate_mission(dict(good_payload, tasks=tasks), request_30)
    assert result.ok, result.issues


def test_generic_title_is_rejected(request_30, good_payload):
    result = validate_mission(dict(good_payload, title="Adventure Awaits"), request_30)
    assert not result.ok
    assert any(i["field"] == "title" and "generic" in i["message"] for i in result.issues)


# --- Request fit: activity, energy, difficulty -------------------------------

def test_high_energy_requires_an_effort_task():
    request = MissionRequest(activity="move", duration_minutes=15, energy="high")
    payload = {
        "title": "Numbers on the Block",
        "description": "A slow loop with three counting games stitched into it.",
        "objective": "Count three kinds of small details you always walk past.",
        "total_duration_minutes": 15,
        "tasks": [
            {"instruction": "Count the red doors on your street within five minutes.",
             "target_minutes": 5},
            {"instruction": "Sketch the strangest texture you can find on a bench.",
             "target_minutes": 5},
            {"instruction": "Name five shopfronts you would never look at twice.",
             "target_minutes": 5},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)
    assert not result.ok
    assert any("physical effort" in i["message"] for i in result.issues), result.issues


def test_high_energy_passes_with_an_effort_task():
    request = MissionRequest(activity="move", duration_minutes=15, energy="high")
    payload = {
        "title": "Stairway Signal Hunt",
        "description": "Climb, count and sketch your way around the block.",
        "objective": "Climb one flight of stairs and spot three numbers on the way.",
        "total_duration_minutes": 15,
        "tasks": [
            {"instruction": "Take the stairs up to the viewpoint and count the steps.",
             "target_minutes": 5},
            {"instruction": "Walk briskly to the bridge and sketch one railing detail.",
             "target_minutes": 5},
            {"instruction": "Find two house numbers older than the building next door.",
             "target_minutes": 5},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)
    assert result.ok, result.issues


def test_low_energy_rejects_vigorous_tasks():
    request = MissionRequest(activity="observe", duration_minutes=30, energy="low")
    payload = {
        "title": "Slow Doorway Census",
        "description": "Three calm, close-looking games on one quiet street.",
        "objective": "Count three kinds of doors and sketch the oldest one you find.",
        "total_duration_minutes": 30,
        "tasks": [
            {"instruction": "Jog around the block twice and count the runners you pass.",
             "target_minutes": 10},
            {"instruction": "Find three doorways with interesting tiles above them.",
             "target_minutes": 10},
            {"instruction": "Sketch the oldest plaque you can spot on this street.",
             "target_minutes": 10},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)
    assert not result.ok
    assert any("vigorous" in i["message"] for i in result.issues), result.issues


def test_move_activity_requires_movement():
    request = MissionRequest(activity="move", duration_minutes=30)
    payload = {
        "title": "Benchside Observatory",
        "description": "Three seated games for watching a street come alive.",
        "objective": "List five kinds of movement you can spot without moving yourself.",
        "total_duration_minutes": 30,
        "tasks": [
            {"instruction": "Sit on a bench and list five kinds of movement you can see.",
             "target_minutes": 10},
            {"instruction": "Count the people who pass within two minutes of you.",
             "target_minutes": 10},
            {"instruction": "Sketch the pattern on the nearest lamppost from here.",
             "target_minutes": 10},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)
    assert not result.ok
    assert any("body moving" in i["message"] for i in result.issues), result.issues


def test_chill_difficulty_rejects_urgency(request_30, good_payload):
    request = MissionRequest(activity="explore_nature", duration_minutes=30, difficulty="chill")
    tasks = [dict(t) for t in good_payload["tasks"]]
    tasks[0]["instruction"] = (
        "Walk to the nearest park and notice three different leaf shapes, racing to "
        "beat your best time."
    )
    result = validate_mission(dict(good_payload, tasks=tasks), request)
    assert not result.ok
    assert any("chill" in i["message"] for i in result.issues), result.issues


def test_push_difficulty_requires_a_stretch():
    request = MissionRequest(activity="observe", duration_minutes=30, difficulty="push")
    payload = {
        "title": "House Number Archive",
        "description": "Three close-looking games along one ordinary block.",
        "objective": "Photograph three house numbers that tell a story about the street.",
        "total_duration_minutes": 30,
        "tasks": [
            {"instruction": "Find three doors with brass numbers on them.",
             "target_minutes": 10},
            {"instruction": "Sketch the strangest texture you find on a wall.",
             "target_minutes": 10},
            {"instruction": "Count the windows that still have flowers in them.",
             "target_minutes": 10},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)
    assert not result.ok
    assert any("push" in i["message"] for i in result.issues), result.issues


# --- Timing window -------------------------------------------------------------

def test_task_sum_must_stay_close_to_requested_duration():
    request = MissionRequest(activity="observe", duration_minutes=30)
    payload = {
        "title": "Window Ledger",
        "description": "Three window games along one long block.",
        "objective": "Log three kinds of windows before you head back home.",
        "total_duration_minutes": 30,
        "tasks": [
            {"instruction": "Count the lit windows you can see from the corner.",
             "target_minutes": 5},
            {"instruction": "Find four curtains that match each other in colour.",
             "target_minutes": 5},
            {"instruction": "Sketch one window box with actual flowers in it.",
             "target_minutes": 5},
            {"instruction": "Name five window shapes you would draw again tomorrow.",
             "target_minutes": 5},
        ],
        "safety_notes": ["Cross roads at crossings and stay on public paths."],
    }
    result = validate_mission(payload, request)  # 20 min of tasks for a 30 min mission
    assert not result.ok
    assert any("task durations add up" in i["message"] for i in result.issues)


# --- JSON extraction ----------------------------------------------------------

def test_extract_json_raw():
    data, err = extract_json('{"title": "x"}')
    assert err is None and data == {"title": "x"}


def test_extract_json_fenced():
    data, err = extract_json('```json\n{"title": "x"}\n```')
    assert err is None and data == {"title": "x"}


def test_extract_json_with_prose():
    data, err = extract_json('Sure! Here is your mission:\n{"title": "x"} Enjoy.')
    assert err is None and data == {"title": "x"}


def test_extract_json_invalid():
    data, err = extract_json("I am sorry, I cannot help with that.")
    assert data is None and err and "JSON" in err


def test_extract_json_empty():
    data, err = extract_json("   ")
    assert data is None and err


# --- Sample mission -----------------------------------------------------------

def test_sample_mission_is_labelled_and_valid(request_30):
    mission = build_sample_mission(request_30)
    assert mission.source == "sample"
    assert mission.provider is None
    assert "Sample" in mission.title
    assert 3 <= len(mission.tasks) <= 5
    assert mission.safety_notes
    assert mission.total_duration_minutes == 30


@pytest.mark.parametrize("minutes", [15, 30, 60])
def test_sample_mission_for_every_duration(minutes):
    request = MissionRequest(activity=ActivityType.explore_nature, duration_minutes=minutes)
    mission = build_sample_mission(request)
    assert mission.total_duration_minutes == minutes
    assert 3 <= len(mission.tasks) <= 5
    total = sum(t.target_minutes for t in mission.tasks)
    assert int(minutes * 0.6) <= total <= int(minutes * 1.4)
