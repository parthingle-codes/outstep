"""Tests for timing logic (the spec mirrored by frontend/src/lib/timing.js)."""

from backend.timing import (
    format_clock,
    is_over_target,
    is_past_planned,
    mission_elapsed_ms,
    planned_ms,
    progress_ratio,
    remaining_ms,
    summarize_run,
    task_elapsed_ms,
)

START = 1_000_000  # ms epoch
MIN = 60_000


def test_planned_ms():
    assert planned_ms(30) == 30 * MIN
    assert planned_ms(0) == 0


def test_elapsed_basic():
    assert mission_elapsed_ms(START + 5 * MIN, START) == 5 * MIN


def test_elapsed_never_negative():
    assert mission_elapsed_ms(START - 1000, START) == 0
    assert mission_elapsed_ms(START, None) == 0


def test_paused_time_is_excluded():
    # 10 min on the clock, but paused for the last 4 min -> 6 min active
    now = START + 10 * MIN
    paused_at = START + 6 * MIN
    assert mission_elapsed_ms(now, START, paused_at_ms=paused_at) == 6 * MIN


def test_accumulated_pause_is_excluded():
    now = START + 30 * MIN
    # one 5 min pause finished earlier (accumulated), plus currently paused 2 min
    assert mission_elapsed_ms(now, START, paused_at_ms=now - 2 * MIN, paused_total_ms=5 * MIN) == 23 * MIN


def test_resume_after_pause_keeps_excluding_paused_time():
    # pause 2-7 min, resume, now at 20 min -> 20 - 5 = 15 min
    resumed_total = 5 * MIN
    assert mission_elapsed_ms(START + 20 * MIN, START, paused_at_ms=None, paused_total_ms=resumed_total) == 15 * MIN


def test_task_elapsed_excludes_task_pause():
    task_started = START + 10 * MIN
    # task ran 4 min, paused 3 min (still paused now) -> 4 min active
    now = task_started + 7 * MIN
    assert task_elapsed_ms(now, task_started, task_paused_at_ms=now - 3 * MIN) == 4 * MIN
    # task ran 4 min, paused 3 min, then resumed for 2 more min -> 6 min active
    assert task_elapsed_ms(now + 2 * MIN, task_started, task_paused_total_ms=3 * MIN) == 6 * MIN


def test_task_pause_before_task_start_does_not_leak_in():
    # mission paused long before the task started; task clock starts clean
    task_started = START + 10 * MIN
    assert task_elapsed_ms(task_started + 5 * MIN, task_started) == 5 * MIN


def test_task_elapsed_none_started():
    assert task_elapsed_ms(START + MIN, None) == 0


def test_remaining_and_past_planned():
    assert remaining_ms(0, 30) == 30 * MIN
    assert remaining_ms(30 * MIN, 30) == 0
    assert remaining_ms(45 * MIN, 30) == 0
    assert not is_past_planned(30 * MIN, 30)
    assert is_past_planned(30 * MIN + 1, 30)


def test_over_target():
    assert not is_over_target(5 * MIN, 5)
    assert is_over_target(5 * MIN + 1, 5)


def test_progress_ratio_clamped():
    assert progress_ratio(0, 30) == 0.0
    assert progress_ratio(15 * MIN, 30) == 0.5
    assert progress_ratio(60 * MIN, 30) == 1.0
    assert progress_ratio(0, 0) == 1.0


def test_format_clock():
    assert format_clock(0) == "0:00"
    assert format_clock(9 * MIN + 5_000) == "9:05"
    assert format_clock(65 * MIN) == "1:05:00"
    assert format_clock(-500) == "0:00"


def test_summarize_run_counts():
    stats = summarize_run(
        ["completed", "skipped", "completed", "pending"],
        elapsed_ms=32 * MIN,
        planned_minutes=30,
    )
    assert stats["total_tasks"] == 4
    assert stats["completed"] == 2
    assert stats["skipped"] == 1
    assert stats["pending"] == 1
    assert stats["completion_rate"] == 0.5
    assert stats["past_planned"] is True  # a fact, never a failure


def test_summarize_run_ontime():
    stats = summarize_run(["completed", "completed"], elapsed_ms=20 * MIN, planned_minutes=30)
    assert stats["past_planned"] is False
    assert stats["completion_rate"] == 1.0
    assert "failed" not in stats  # running late is never a failure state


def test_summarize_run_empty():
    stats = summarize_run([], elapsed_ms=0, planned_minutes=15)
    assert stats["total_tasks"] == 0
    assert stats["completion_rate"] == 0.0
