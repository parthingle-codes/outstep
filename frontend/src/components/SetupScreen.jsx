import { useState } from 'react'

import { ActivityIcon, Logo } from './Icons.jsx'
import {
  ACTIVITIES,
  DIFFICULTIES,
  DURATIONS,
  ENERGY_LEVELS,
} from '../constants.js'

function ChoiceGrid({ options, value, onChange, columns = 'two' }) {
  return (
    <div className={`choice-grid choice-grid--${columns}`}>
      {options.map((option) => {
        const active = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            className={`choice ${active ? 'is-active' : ''}`}
            onClick={() => onChange(option.id)}
            aria-pressed={active}
          >
            <span className="choice__label">{option.label}</span>
            {option.blurb && <span className="choice__blurb">{option.blurb}</span>}
          </button>
        )
      })}
    </div>
  )
}

function ErrorBanner({ error, onRetry, onSample }) {
  if (!error) return null
  return (
    <div className="banner banner--error" role="alert">
      <strong>Generation failed.</strong> {error.message}
      {error.issues?.length > 0 && (
        <ul className="banner__issues">
          {error.issues.slice(0, 5).map((issue, i) => (
            <li key={i}>
              <code>{issue.field}</code> — {issue.message}
            </li>
          ))}
        </ul>
      )}
      <div className="banner__actions">
        <button type="button" className="btn btn--secondary btn--sm" onClick={onRetry}>
          Try again
        </button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onSample}>
          Use the labelled sample instead
        </button>
      </div>
    </div>
  )
}

export default function SetupScreen({
  prefs,
  setPrefs,
  onGenerate,
  onSample,
  error,
  busy,
  sampleAvailable = true,
}) {
  const [showAdvanced, setShowAdvanced] = useState(Boolean(prefs.context))

  const update = (patch) => setPrefs({ ...prefs, ...patch })

  return (
    <div className="screen screen--setup">
      <header className="hero">
        <div className="brand">
          <span className="brand__mark">
            <Logo size={34} />
          </span>
          <span className="brand__name">OutStep</span>
        </div>
        <p className="hero__tagline">Step out. Experience more.</p>
        <p className="hero__philosophy">
          The AI plans the adventure. The app tracks the adventure. The human experiences the
          adventure.
        </p>
      </header>

      <section className="section">
        <p className="eyebrow">Step 1</p>
        <h2 className="section__title">What kind of mission?</h2>
        <div className="activity-grid">
          {ACTIVITIES.map((activity) => {
            const active = activity.id === prefs.activity
            return (
              <button
                key={activity.id}
                type="button"
                className={`activity ${active ? 'is-active' : ''}`}
                onClick={() => update({ activity: activity.id })}
                aria-pressed={active}
              >
                <span className="activity__icon">
                  <ActivityIcon name={activity.id} />
                </span>
                <span className="activity__label">{activity.label}</span>
                <span className="activity__blurb">{activity.blurb}</span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="section">
        <p className="eyebrow">Step 2</p>
        <h2 className="section__title">How long have you got?</h2>
        <div className="segmented">
          {DURATIONS.map((minutes) => {
            const active = minutes === prefs.durationMinutes
            return (
              <button
                key={minutes}
                type="button"
                className={`segmented__item ${active ? 'is-active' : ''}`}
                onClick={() => update({ durationMinutes: minutes })}
                aria-pressed={active}
              >
                {minutes}
                <span className="segmented__unit">min</span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="section">
        <p className="eyebrow">Step 3</p>
        <h2 className="section__title">Energy &amp; difficulty</h2>
        <div className="field">
          <span className="field__label">Energy level</span>
          <ChoiceGrid
            options={ENERGY_LEVELS}
            value={prefs.energy}
            onChange={(energy) => update({ energy })}
            columns="three"
          />
        </div>
        <div className="field">
          <span className="field__label">Difficulty</span>
          <ChoiceGrid
            options={DIFFICULTIES}
            value={prefs.difficulty}
            onChange={(difficulty) => update({ difficulty })}
            columns="three"
          />
        </div>
      </section>

      <section className="section">
        <button
          type="button"
          className="disclosure"
          onClick={() => setShowAdvanced((value) => !value)}
          aria-expanded={showAdvanced}
        >
          <span>{showAdvanced ? 'Hide' : 'Add'} extra context (optional)</span>
          <span className="disclosure__chevron" aria-hidden="true">
            {showAdvanced ? '−' : '+'}
          </span>
        </button>
        {showAdvanced && (
          <div className="field">
            <label className="field__label" htmlFor="context">
              Anything the model should know?
            </label>
            <textarea
              id="context"
              className="textarea"
              rows={3}
              maxLength={400}
              placeholder="e.g. I'm with my dog, recovering from a long week, no hills please"
              value={prefs.context}
              onChange={(event) => update({ context: event.target.value })}
            />
            <span className="field__hint">{prefs.context.length}/400 characters</span>
          </div>
        )}
      </section>

      <ErrorBanner error={error} onRetry={onGenerate} onSample={onSample} />

      <div className="cta">
        <button
          type="button"
          className="btn btn--primary btn--block"
          onClick={onGenerate}
          disabled={busy}
        >
          {busy ? 'Generating…' : 'Generate my mission'}
        </button>
        {sampleAvailable && (
          <button
            type="button"
            className="btn btn--ghost btn--block"
            onClick={onSample}
            disabled={busy}
          >
            Skip the AI — show me the sample mission
          </button>
        )}
        <p className="cta__note">
          Missions are generated by an open-weight model, then checked by deterministic safety
          rules before they reach you.
        </p>
      </div>
    </div>
  )
}
