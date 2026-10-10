"""Tests for deterministic mission validation and safety checks."""

import pytest

from backend.schemas import ActivityType, CompletionMode, MissionRequest
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
