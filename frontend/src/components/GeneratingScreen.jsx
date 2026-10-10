import { useEffect, useState } from 'react'

const STEPS = [
  'Waking up the model…',
  'Sketching your route…',
  'Fitting tasks to your time…',
  'Checking safety notes…',
  'Validating the mission…',
]

export default function GeneratingScreen({ durationMinutes, onCancel }) {
  const [step, setStep] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setStep((value) => (value + 1) % STEPS.length), 2600)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="screen screen--generating" aria-busy="true">
      <div className="generating">
        <span className="generating__spinner" aria-hidden="true" />
        <p className="generating__status" aria-live="polite">
          {STEPS[step]}
        </p>
        <p className="generating__hint">
          Building a {durationMinutes}-minute outdoor mission with your configured open-weight
          model. This can take up to a minute on the first run.
        </p>

        <div className="skeleton-card">
          <div className="skeleton skeleton--title" />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line skeleton--short" />
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>

        <button type="button" className="btn btn--ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
