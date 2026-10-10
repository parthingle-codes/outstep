"""Pure timing logic for mission/task tracking.

These functions are the *specification* for how OutStep measures time. The
frontend mirrors them 1:1 in `frontend/src/lib/timing.js`, and the rules are
covered by `backend/tests/test_timing.py`.

Design rules:
  * Elapsed time is ALWAYS derived from saved timestamps (never from a ticking
    counter), so a backgrounded tab, a refresh, or a suspended phone cannot
    corrupt the clock.
  * Paused time is excluded: (now - started) - time spent paused.
  * Running late is never a failure. There is no "failed" state -- only
    `past_planned`, which simply unlocks extra options for the user.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

MS_PER_MINUTE = 60_000


def planned_ms(planned_minutes: int) -> int:
    """Planned mission duration in milliseconds."""
    return max(0, int(planned_minutes)) * MS_PER_MINUTE


def mission_elapsed_ms(
    now_ms: int,
    started_at_ms: Optional[int],
    paused_at_ms: Optional[int] = None,
    paused_total_ms: int = 0,
) -> int:
    """Elapsed mission time in ms, excluding any paused time. Never negative."""
    if started_at_ms is None:
        return 0
    elapsed = int(now_ms) - int(started_at_ms)
    if paused_at_ms is not None:
        elapsed -= int(now_ms) - int(paused_at_ms)
    elapsed -= max(0, int(paused_total_ms))
    return max(0, elapsed)


def task_elapsed_ms(
    now_ms: int,
    task_started_at_ms: Optional[int],
    task_paused_at_ms: Optional[int] = None,
    task_paused_total_ms: int = 0,
) -> int:
    """Elapsed time for one task from its own saved timestamps.

    Tasks carry their own pause fields (pausing the mission while a task is
    running pauses that task too), so pauses that happen *before* a task starts
    never distort its clock.
    """
    return mission_elapsed_ms(now_ms, task_started_at_ms, task_paused_at_ms, task_paused_total_ms)


def remaining_ms(elapsed_ms: int, planned_minutes: int) -> int:
    """Milliseconds left before the planned duration is used up (never negative)."""
    return max(0, planned_ms(planned_minutes) - max(0, int(elapsed_ms)))


def is_past_planned(elapsed_ms: int, planned_minutes: int) -> bool:
    """True once the user has gone past the planned time. Not a failure."""
    return int(elapsed_ms) > planned_ms(planned_minutes)


def is_over_target(task_elapsed_ms_value: int, target_minutes: int) -> bool:
    """True once a single task has passed its own target duration."""
    return int(task_elapsed_ms_value) > planned_ms(target_minutes)


def progress_ratio(elapsed_ms: int, planned_minutes: int) -> float:
    """0.0 - 1.0 progress through the planned duration (clamped, never > 1)."""
    total = planned_ms(planned_minutes)
    if total <= 0:
        return 1.0
    return min(1.0, max(0.0, int(elapsed_ms) / total))


def format_clock(elapsed_ms: int) -> str:
    """Human clock text: `M:SS` under an hour, `H:MM:SS` beyond it."""
    total_seconds = max(0, int(elapsed_ms)) // 1000
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def summarize_run(
    task_statuses: Iterable[str],
    elapsed_ms: int,
    planned_minutes: int,
) -> dict:
    """Completion summary stats.

    Time is a guide, not a punishment: the result reports `past_planned`
    as a fact, never a pass/fail verdict.
    """
    statuses = list(task_statuses)
    total = len(statuses)
    completed = sum(1 for s in statuses if s == "completed")
    skipped = sum(1 for s in statuses if s == "skipped")
    pending = sum(1 for s in statuses if s in ("pending", "in_progress"))
    return {
        "total_tasks": total,
        "completed": completed,
        "skipped": skipped,
        "pending": pending,
        "completion_rate": (completed / total) if total else 0.0,
        "elapsed_ms": max(0, int(elapsed_ms)),
        "planned_minutes": int(planned_minutes),
        "past_planned": is_past_planned(elapsed_ms, planned_minutes),
    }


def status_counts(statuses: Iterable[str]) -> Mapping[str, int]:
    """Small helper used by tests and future reporting."""
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return counts
