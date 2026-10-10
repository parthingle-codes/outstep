import { useCallback, useEffect, useState } from 'react'

import SetupScreen from './components/SetupScreen.jsx'
import GeneratingScreen from './components/GeneratingScreen.jsx'
import MissionCard from './components/MissionCard.jsx'
import ActiveScreen from './components/ActiveScreen.jsx'
import SummaryScreen from './components/SummaryScreen.jsx'
import HistoryScreen from './components/HistoryScreen.jsx'
import { fetchConfig, fetchSampleMission, generateMission } from './api.js'
import {
  clearActiveRun,
  loadActiveRun,
  loadHistory,
  loadPrefs,
  saveActiveRun,
  savePrefs,
  upsertHistoryEntry,
} from './storage.js'
import { DEFAULT_PREFS } from './constants.js'
import { missionElapsedMs, summarizeRun, taskElapsedMs } from './lib/timing.js'

export default function App() {
  const [prefs, setPrefsState] = useState(() => ({ ...DEFAULT_PREFS, ...(loadPrefs() || {}) }))
  const [history, setHistory] = useState(loadHistory)
  const [run, setRun] = useState(loadActiveRun)
  const [mission, setMission] = useState(null)
  const [finishedEntry, setFinishedEntry] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [config, setConfig] = useState(null)
  const [view, setView] = useState(() => (loadActiveRun() ? 'active' : 'setup'))
  const [now, setNow] = useState(() => Date.now())

  const setPrefs = (next) => {
    setPrefsState(next)
    savePrefs(next)
  }

  /* Re-render once a second while a mission runs; elapsed time itself is always
     derived from saved timestamps, never incremented. */
  useEffect(() => {
    if (view !== 'active') return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    const onWake = () => setNow(Date.now())
    document.addEventListener('visibilitychange', onWake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onWake)
    }
  }, [view])

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(() => setConfig(null))
  }, [])

  const updateRun = useCallback((mutator) => {
    setRun((previous) => {
      if (!previous) return previous
      const next = typeof mutator === 'function' ? mutator(previous) : mutator
      saveActiveRun(next)
      return next
    })
  }, [])

  const payload = {
    activity: prefs.activity,
    duration_minutes: prefs.durationMinutes,
    energy: prefs.energy,
    difficulty: prefs.difficulty,
    context: prefs.context,
  }

  const handleGenerate = async () => {
    setBusy(true)
    setError(null)
    setView('generating')
    try {
      const response = await generateMission(payload)
      setMission(response.mission)
      setView('preview')
    } catch (err) {
      setError({ message: err.message, issues: err.issues || [] })
      setView('setup')
    } finally {
      setBusy(false)
    }
  }

  const handleSample = async () => {
    if (config && config.sample_available === false) return
    setBusy(true)
    setError(null)
    setView('generating')
    try {
      const response = await fetchSampleMission(payload)
      setMission(response.mission)
      setView('preview')
    } catch (err) {
      setError({ message: err.message, issues: err.issues || [] })
      setView('setup')
    } finally {
      setBusy(false)
    }
  }

  const handleCancelGeneration = () => {
    setBusy(false)
    setError(null)
    setView('setup')
  }

  /* --- Running the mission (all local: no AI is needed once started) -------- */

  const handleStartMission = () => {
    if (!mission) return
    const tasks = {}
    for (const task of mission.tasks) {
      tasks[task.id] = {
        status: 'pending',
        startedAt: null,
        pausedAt: null,
        pausedTotalMs: 0,
        finishedAt: null,
        durationMs: null,
      }
    }
    const newRun = {
      version: 1,
      mission,
      status: 'active',
      startedAt: Date.now(),
      pausedAt: null,
      pausedTotalMs: 0,
      currentTaskId: null,
      overtimeAck: false,
      tasks,
    }
    saveActiveRun(newRun)
    setRun(newRun)
    setNow(Date.now())
    setView('active')
  }

  const handleStartTask = (taskId) => {
    const stamp = Date.now()
    updateRun((previous) => ({
      ...previous,
      currentTaskId: taskId,
      tasks: {
        ...previous.tasks,
        [taskId]: {
          ...previous.tasks[taskId],
          status: 'in_progress',
          startedAt: stamp,
          pausedAt: null,
          pausedTotalMs: 0,
        },
      },
    }))
    setNow(stamp)
  }

  const handleCompleteTask = (taskId) => {
    const stamp = Date.now()
    updateRun((previous) => {
      const state = previous.tasks[taskId]
      const startedAt = state.startedAt ?? stamp
      return {
        ...previous,
        currentTaskId: null,
        tasks: {
          ...previous.tasks,
          [taskId]: {
            ...state,
            status: 'completed',
            startedAt,
            pausedAt: null,
            finishedAt: stamp,
            durationMs: taskElapsedMs(stamp, startedAt, state.pausedAt, state.pausedTotalMs),
          },
        },
      }
    })
    setNow(stamp)
  }

  const handleSkipTask = (taskId) => {
    const stamp = Date.now()
    updateRun((previous) => {
      const state = previous.tasks[taskId]
      const startedAt = state.startedAt
      return {
        ...previous,
        currentTaskId: null,
        tasks: {
          ...previous.tasks,
          [taskId]: {
            ...state,
            status: 'skipped',
            pausedAt: null,
            finishedAt: stamp,
            durationMs: startedAt
              ? taskElapsedMs(stamp, startedAt, state.pausedAt, state.pausedTotalMs)
              : 0,
          },
        },
      }
    })
    setNow(stamp)
  }

  const handlePause = () => {
    const stamp = Date.now()
    updateRun((previous) => {
      const tasks = { ...previous.tasks }
      if (previous.currentTaskId && tasks[previous.currentTaskId].status === 'in_progress') {
        tasks[previous.currentTaskId] = {
          ...tasks[previous.currentTaskId],
          pausedAt: stamp,
        }
      }
      return { ...previous, pausedAt: stamp, tasks }
    })
  }

  const handleResume = () => {
    const stamp = Date.now()
    updateRun((previous) => {
      if (previous.pausedAt == null) return previous
      const tasks = { ...previous.tasks }
      if (previous.currentTaskId && tasks[previous.currentTaskId].pausedAt != null) {
        const state = tasks[previous.currentTaskId]
        tasks[previous.currentTaskId] = {
          ...state,
          pausedAt: null,
          pausedTotalMs: state.pausedTotalMs + (stamp - state.pausedAt),
        }
      }
      return {
        ...previous,
        pausedAt: null,
        pausedTotalMs: previous.pausedTotalMs + (stamp - previous.pausedAt),
        tasks,
      }
    })
  }

  const handleKeepGoing = () => updateRun((previous) => ({ ...previous, overtimeAck: true }))

  const finishRun = (status) => {
    const stamp = Date.now()
    if (!run) return
    const elapsed = missionElapsedMs(stamp, run.startedAt, run.pausedAt, run.pausedTotalMs)
    const taskResults = run.mission.tasks.map((task) => ({
      id: task.id,
      instruction: task.instruction,
      target_minutes: task.target_minutes,
      completion_mode: task.completion_mode,
      status: run.tasks[task.id].status,
      durationMs: run.tasks[task.id].durationMs,
    }))
    const stats = summarizeRun(
      taskResults.map((task) => task.status),
      elapsed,
      run.mission.total_duration_minutes,
    )
    const entry = {
      id: `run-${stamp}`,
      finishedAt: stamp,
      status,
      mission: run.mission,
      taskResults,
      stats,
      reflection: '',
    }
    const updatedHistory = upsertHistoryEntry(entry)
    clearActiveRun()
    setHistory(updatedHistory)
    setFinishedEntry(entry)
    setRun(null)
    setNow(stamp)
    setView('summary')
  }

  const handleSaveReflection = (entryId, text) => {
    const existing = history.find((entry) => entry.id === entryId)
    if (!existing) return
    const updated = upsertHistoryEntry({ ...existing, reflection: text })
    setHistory(updated)
    setFinishedEntry((current) => (current?.id === entryId ? { ...current, reflection: text } : current))
  }

  const handleOpenHistoryEntry = (entry) => {
    setFinishedEntry(entry)
    setView('summary')
  }

  const handleNewMission = () => {
    setMission(null)
    setFinishedEntry(null)
    setError(null)
    setView('setup')
  }

  /* --- Render -------------------------------------------------------------- */

  const sampleAllowed = !config || config.sample_available !== false

  return (
    <div className={`app-shell view-${view}`}>
      <main className="app-main">
        {view === 'setup' && (
          <SetupScreen
            prefs={prefs}
            setPrefs={setPrefs}
            onGenerate={handleGenerate}
            onSample={handleSample}
            error={error}
            busy={busy}
            sampleAvailable={sampleAllowed}
          />
        )}

        {view === 'generating' && (
          <GeneratingScreen
            durationMinutes={prefs.durationMinutes}
            onCancel={handleCancelGeneration}
          />
        )}

        {view === 'preview' && mission && (
          <div className="screen screen--preview">
            <p className="eyebrow">Your mission is ready</p>
            <MissionCard mission={mission}>
              <button
                type="button"
                className="btn btn--primary btn--block"
                onClick={handleStartMission}
              >
                Start mission
              </button>
              <div className="preview-actions">
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={handleGenerate}
                  disabled={busy}
                >
                  Regenerate
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={handleNewMission}
                >
                  Back to setup
                </button>
              </div>
              <p className="cta__note">
                Once you start, everything runs on your device — you can put your phone away.
              </p>
            </MissionCard>
          </div>
        )}

        {view === 'active' && run && (
          <ActiveScreen
            run={run}
            now={now}
            onStartTask={handleStartTask}
            onCompleteTask={handleCompleteTask}
            onSkipTask={handleSkipTask}
            onPause={handlePause}
            onResume={handleResume}
            onEndEarly={() => finishRun('ended_early')}
            onFinish={() => finishRun('completed')}
            onKeepGoing={handleKeepGoing}
          />
        )}

        {view === 'summary' && finishedEntry && (
          <SummaryScreen
            entry={finishedEntry}
            onSaveReflection={handleSaveReflection}
            onNewMission={handleNewMission}
            onOpenHistory={() => setView('history')}
          />
        )}

        {view === 'history' && (
          <HistoryScreen
            history={history}
            onBack={() => setView(run ? 'active' : 'setup')}
            onView={handleOpenHistoryEntry}
          />
        )}
      </main>

      {(view === 'setup' || view === 'preview') && (
        <footer className="app-footer">
          <span>
            {config ? `AI: ${config.provider_label}` : 'AI: checking provider…'}
            {!sampleAllowed && ' · sample disabled'}
          </span>
          <span className="app-footer__links">
            <button type="button" className="link" onClick={() => setView('history')}>
              History ({history.length})
            </button>
          </span>
        </footer>
      )}
    </div>
  )
}
