import { useState } from 'react'

import { SourceBadge, TaskStatusIcon } from './MissionCard.jsx'
import { Logo } from './Icons.jsx'
import { activityLabel } from '../constants.js'
import { formatClock, formatDuration } from '../lib/timing.js'

export default function SummaryScreen({ entry, onSaveReflection, onNewMission, onOpenHistory }) {
  const [reflection, setReflection] = useState(entry.reflection || '')
  const [saved, setSaved] = useState(Boolean(entry.reflection))
  const mission = entry.mission
  const stats = entry.stats
  const finishedEarly = entry.status === 'ended_early'

  const save = () => {
    onSaveReflection(entry.id, reflection)
    setSaved(true)
  }

  return (
    <div className="screen screen--summary">
      <header className="summary-head">
        <span className="brand__mark brand__mark--center">
          <Logo size={40} />
        </span>
        <p className="eyebrow">{finishedEarly ? 'Mission wrapped up early' : 'Mission complete'}</p>
        <h1 className="summary-head__title">{mission.title}</h1>
        <div className="summary-head__badges">
          <SourceBadge mission={mission} />
          <span className="pill">{activityLabel(mission.activity)}</span>
        </div>
      </header>

      <section className="stats">
        <div className="stat">
          <span className="stat__value">{formatDuration(stats.elapsed_ms)}</span>
          <span className="stat__label">time outside</span>
        </div>
        <div className="stat">
          <span className="stat__value">
            {stats.completed}/{stats.total_tasks}
          </span>
          <span className="stat__label">tasks completed</span>
        </div>
        <div className="stat">
          <span className="stat__value">{stats.skipped}</span>
          <span className="stat__label">skipped (fine!)</span>
        </div>
        <div className="stat">
          <span className="stat__value">{stats.planned_minutes} min</span>
          <span className="stat__label">
            planned{stats.past_planned ? ' · ran longer' : ''}
          </span>
        </div>
      </section>

      <p className="summary-note">
        {stats.past_planned
          ? 'You went past the planned time and finished anyway — that counts as a win.'
          : 'You finished inside the planned window. Nicely paced.'}
        {stats.skipped > 0 && ' Skipped tasks are part of the plan, not a failure.'}
      </p>

      <section className="section">
        <p className="eyebrow">What you did</p>
        <ul className="task-rows task-rows--light">
          {entry.taskResults.map((task, index) => (
            <li key={task.id} className={`task-row is-${task.status}`}>
              <TaskStatusIcon status={task.status} />
              <span className="task-row__index">{index + 1}</span>
              <span className="task-row__instruction">{task.instruction}</span>
              <span className="task-row__target">
                {task.status === 'completed' && task.durationMs
                  ? formatClock(task.durationMs)
                  : `${task.target_minutes}′`}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="section reflection">
        <p className="eyebrow">Optional reflection</p>
        <h2 className="section__title">What did you notice out there?</h2>
        <textarea
          className="textarea"
          rows={4}
          maxLength={600}
          placeholder="One sentence is plenty. This stays on your device."
          value={reflection}
          onChange={(event) => {
            setReflection(event.target.value)
            setSaved(false)
          }}
        />
        <div className="reflection__actions">
          <button type="button" className="btn btn--secondary" onClick={save} disabled={saved}>
            {saved ? 'Saved ✓' : 'Save reflection'}
          </button>
          <span className="field__hint">Stored only in this browser.</span>
        </div>
      </section>

      <div className="cta">
        <button type="button" className="btn btn--primary btn--block" onClick={onNewMission}>
          Plan another mission
        </button>
        <button type="button" className="btn btn--ghost btn--block" onClick={onOpenHistory}>
          View history
        </button>
      </div>
    </div>
  )
}
