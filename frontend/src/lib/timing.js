/**
 * Timing helpers — the browser mirror of `backend/timing.py`.
 *
 * Rules:
 *  - Elapsed time is always derived from saved timestamps, never from a
 *    ticking counter, so refreshes / backgrounded tabs cannot corrupt it.
 *  - Paused time is excluded.
 *  - Running late is never a failure (no "failed" state exists).
 */

export const MS_PER_MINUTE = 60_000

export function plannedMs(plannedMinutes) {
  return Math.max(0, Number(plannedMinutes) || 0) * MS_PER_MINUTE
}

export function missionElapsedMs(nowMs, startedAtMs, pausedAtMs = null, pausedTotalMs = 0) {
  if (startedAtMs == null) return 0
  let elapsed = nowMs - startedAtMs
  if (pausedAtMs != null) elapsed -= nowMs - pausedAtMs
  elapsed -= Math.max(0, pausedTotalMs)
  return Math.max(0, elapsed)
}

export function taskElapsedMs(nowMs, taskStartedAtMs, pausedAtMs = null, pausedTotalMs = 0) {
  return missionElapsedMs(nowMs, taskStartedAtMs, pausedAtMs, pausedTotalMs)
}

export function remainingMs(elapsedMs, plannedMinutes) {
  return Math.max(0, plannedMs(plannedMinutes) - Math.max(0, elapsedMs))
}

export function isPastPlanned(elapsedMs, plannedMinutes) {
  return elapsedMs > plannedMs(plannedMinutes)
}

export function isOverTarget(taskElapsedMs, targetMinutes) {
  return taskElapsedMs > plannedMs(targetMinutes)
}

export function progressRatio(elapsedMs, plannedMinutes) {
  const total = plannedMs(plannedMinutes)
  if (total <= 0) return 1
  return Math.min(1, Math.max(0, elapsedMs / total))
}

export function formatClock(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(seconds).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`
}

export function formatDuration(ms) {
  const totalMinutes = Math.round(Math.max(0, ms) / MS_PER_MINUTE)
  if (totalMinutes < 1) return 'under a minute'
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours && minutes) return `${hours} h ${minutes} min`
  if (hours) return `${hours} h`
  return `${minutes} min`
}

/** Completion summary. Never yields a pass/fail verdict — only facts. */
export function summarizeRun(taskStatuses, elapsedMs, plannedMinutes) {
  const statuses = [...taskStatuses]
  const total = statuses.length
  const completed = statuses.filter((s) => s === 'completed').length
  const skipped = statuses.filter((s) => s === 'skipped').length
  const pending = statuses.filter((s) => s === 'pending' || s === 'in_progress').length
  return {
    total_tasks: total,
    completed,
    skipped,
    pending,
    completion_rate: total ? completed / total : 0,
    elapsed_ms: Math.max(0, elapsedMs),
    planned_minutes: plannedMinutes,
    past_planned: isPastPlanned(elapsedMs, plannedMinutes),
  }
}
