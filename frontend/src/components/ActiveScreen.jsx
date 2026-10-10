import { useEffect, useMemo, useRef } from 'react'

import { SafetyNotes, TaskStatusIcon } from './MissionCard.jsx'
import {
  CheckIcon,
  ClockIcon,
  FlagIcon,
  PauseIcon,
  PlayIcon,
  SkipIcon,
} from './Icons.jsx'
import {
  formatClock,
  isOverTarget,
  isPastPlanned,
  missionElapsedMs,
  progressRatio,
  remainingMs,
  taskElapsedMs,
} from '../lib/timing.js'

export default function ActiveScreen({
  run,
  now,
  onStartTask,
  onCompleteTask,
  onSkipTask,
  onPause,
  onResume,
  onEndEarly,
  onFinish,
  onKeepGoing,
}) {
  const mission = run.mission
  const planned = mission.total_duration_minutes
  const paused = run.pausedAt != null
  const elapsed = missionElapsedMs(now, run.startedAt, run.pausedAt, run.pausedTotalMs)
  const pastPlanned = isPastPlanned(elapsed, planned)
  const ratio = progressRatio(elapsed, planned)

  const taskStates = mission.tasks.map((task) => ({
    task,
    state: run.tasks[task.id] || { status: 'pending' },
  }))
  const current =
    taskStates.find(({ state }) => state.status === 'in_progress') ||
    taskStates.find(({ state }) => state.status === 'pending') ||
    null
  const allDone = taskStates.every(({ state }) =>
    ['completed', 'skipped'].includes(state.status),
  )

  const currentElapsed = current
    ? taskElapsedMs(now, current.state.startedAt, current.state.pausedAt, current.state.pausedTotalMs)
    : 0

  // Keep the screen awake while the mission runs (best-effort, ignored if unsupported).
  const wakeLockRef = useRef(null)
  useEffect(() => {
    let cancelled = false
    async function request() {
      try {
        if ('wakeLock' in navigator) {
          const lock = await navigator.wakeLock.request('screen')
          if (cancelled) lock.release?.()
          else wakeLockRef.current = lock
        }
      } catch {
        /* not supported / permission denied — the timer still works */
      }
    }
    request()
    return () => {
      cancelled = true
      try {
        wakeLockRef.current?.release?.()
      } catch {
        /* ignore */
      }
      wakeLockRef.current = null
    }
  }, [])

  const remainingLabel = useMemo(() => {
    if (!current) return null
    const targetMs = current.task.target_minutes * 60_000
    const left = remainingMs(currentElapsed, current.task.target_minutes)
    return { targetMs, left, showCountdown: current.task.completion_mode === 'timer' }
  }, [current, currentElapsed])

  const statusLabel = paused
    ? 'Paused'
    : pastPlanned
      ? 'Past planned time — no rush'
      : 'On track'

  return (
    <div className="screen screen--active">
      <header className="active-head">
        <div className="active-head__row">
          <span className="eyebrow eyebrow--light">{mission.title}</span>
          <span className={`status-pill ${paused ? 'is-paused' : pastPlanned ? 'is-late' : ''}`}>
            {statusLabel}
          </span>
        </div>

        <div className="big-clock" aria-live="off">
          {formatClock(elapsed)}
        </div>
        <p className="big-clock__caption">
          of {planned} min planned · {Math.round(ratio * 100)}%
        </p>

        <div className="progress">
          <div
            className={`progress__fill ${pastPlanned ? 'is-late' : ''}`}
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </div>

        {pastPlanned && !run.overtimeAck && (
          <div className="overtime" role="status">
            <p className="overtime__title">You’re past the planned time — that’s completely fine.</p>
            <p className="overtime__body">Time is a guide, not a grade. Pick what fits:</p>
            <div className="overtime__actions">
              <button type="button" className="btn btn--light btn--sm" onClick={onKeepGoing}>
                Keep going
              </button>
              <button
                type="button"
                className="btn btn--outline-light btn--sm"
                onClick={() => current && onSkipTask(current.task.id)}
                disabled={!current || paused}
              >
                Skip this task
              </button>
              <button
                type="button"
                className="btn btn--outline-light btn--sm"
                onClick={onEndEarly}
              >
                Finish now
              </button>
            </div>
          </div>
        )}
      </header>

      {current && (
        <section className="current-task">
          <p className="eyebrow eyebrow--light">
            Task {mission.tasks.findIndex((t) => t.id === current.task.id) + 1} of{' '}
            {mission.tasks.length}
            {current.task.completion_mode === 'timer' ? ' · timer' : ' · tap when done'}
          </p>
          <p className="current-task__instruction">{current.task.instruction}</p>

          <div className="current-task__time">
            {current.state.status === 'in_progress' ? (
              remainingLabel?.showCountdown ? (
                <span className={`countdown ${remainingLabel.left <= 0 ? 'is-done' : ''}`}>
                  {remainingLabel.left > 0
                    ? formatClock(remainingLabel.left)
                    : 'Time’s up'}
                  <span className="countdown__caption">
                    {remainingLabel.left > 0
                      ? 'left on the timer'
                      : 'mark it done whenever you like'}
                  </span>
                </span>
              ) : (
                <span className="countdown">
                  {formatClock(currentElapsed)}
                  <span className="countdown__caption">elapsed on this task</span>
                </span>
              )
            ) : (
              <span className="countdown">
                ~{current.task.target_minutes}:00
                <span className="countdown__caption">target for this task</span>
              </span>
            )}

            {current.state.status === 'in_progress' &&
              isOverTarget(currentElapsed, current.task.target_minutes) && (
                <span className="over-target">Over target — no penalty, finish when ready.</span>
              )}
          </div>

          <div className="current-task__actions">
            {current.state.status === 'pending' ? (
              <>
                <button
                  type="button"
                  className="btn btn--light btn--block"
                  onClick={() => onStartTask(current.task.id)}
                  disabled={paused}
                >
                  <PlayIcon /> Start this task
                </button>
                <button
                  type="button"
                  className="btn btn--outline-light btn--block"
                  onClick={() => onSkipTask(current.task.id)}
                  disabled={paused}
                >
                  <SkipIcon /> Skip
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn--light btn--block"
                  onClick={() => onCompleteTask(current.task.id)}
                  disabled={paused}
                >
                  <CheckIcon /> Mark done
                </button>
                <button
                  type="button"
                  className="btn btn--outline-light btn--block"
                  onClick={() => onSkipTask(current.task.id)}
                  disabled={paused}
                >
                  <SkipIcon /> Skip
                </button>
              </>
            )}
          </div>
        </section>
      )}

      <section className="task-progress">
        <p className="eyebrow eyebrow--light">Your tasks</p>
        <ul className="task-rows">
          {taskStates.map(({ task, state }, index) => {
            const isCurrent = current?.task.id === task.id
            return (
              <li
                key={task.id}
                className={`task-row ${isCurrent ? 'is-current' : ''} is-${state.status}`}
              >
                <TaskStatusIcon status={state.status} />
                <span className="task-row__index">{index + 1}</span>
                <span className="task-row__instruction">{task.instruction}</span>
                <span className="task-row__target">{task.target_minutes}′</span>
              </li>
            )
          })}
        </ul>

        {allDone && (
          <div className="all-done" role="status">
            <p className="all-done__title">Every task is wrapped up.</p>
            <button type="button" className="btn btn--accent btn--block" onClick={onFinish}>
              <FlagIcon /> Finish mission &amp; see summary
            </button>
          </div>
        )}
      </section>

      <section className="active-controls">
        <button
          type="button"
          className="btn btn--outline-light btn--block"
          onClick={paused ? onResume : onPause}
        >
          {paused ? <PlayIcon /> : <PauseIcon />} {paused ? 'Resume mission' : 'Pause mission'}
        </button>
        <div className="active-controls__secondary">
          <button
            type="button"
            className="btn btn--ghost-light btn--sm"
            onClick={onEndEarly}
            disabled={allDone}
          >
            <FlagIcon /> End early
          </button>
          {!allDone && (
            <button
              type="button"
              className="btn btn--ghost-light btn--sm"
              onClick={onFinish}
            >
              Finish now
            </button>
          )}
          <span className="active-controls__note">
            <ClockIcon size={14} /> Progress saves on this device
          </span>
        </div>
      </section>

      <SafetyNotes notes={mission.safety_notes} />
    </div>
  )
}
