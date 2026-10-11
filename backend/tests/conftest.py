"""Shared pytest fixtures."""

import sys
from pathlib import Path

import pytest

# Make the repository root importable no matter where pytest is run from.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import MissionRequest  # noqa: E402


@pytest.fixture
def request_30() -> MissionRequest:
    return MissionRequest(activity="explore_nature", duration_minutes=30)


@pytest.fixture
def request_15() -> MissionRequest:
    return MissionRequest(activity="move", duration_minutes=15, energy="high", difficulty="push")


@pytest.fixture
def good_payload() -> dict:
    return {
        "title": "Green Loop Discovery",
        "description": "A relaxed walk with three small noticing games along the way.",
        "objective": "Come home able to name three details on your street you had never noticed.",
        "archetype": "nature_bingo",
        "total_duration_minutes": 30,
        "completion_mode": "manual",
        "tasks": [
            {"instruction": "Walk to the nearest park and notice three different leaf shapes.",
             "target_minutes": 8, "completion_mode": "timer"},
            {"instruction": "Stand still for two minutes and count the sounds you can hear.",
             "target_minutes": 6, "completion_mode": "timer"},
            {"instruction": "Find a bench and write one sentence about the light today.",
             "target_minutes": 10, "completion_mode": "manual"},
            {"instruction": "Take a slow loop back home and count the doorways you pass "
             "on the way.",
             "target_minutes": 6, "completion_mode": "manual"},
        ],
        "safety_notes": [
            "Stay on public paths and watch for cyclists.",
            "Carry water if it is warm.",
        ],
    }
