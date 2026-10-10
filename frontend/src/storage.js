/**
 * Local-only persistence (browser localStorage).
 *
 * Everything about the user's run lives on the device: the active mission,
 * task states, timestamps, and history. No account, no server sync.
 */

const KEYS = {
  active: 'outstep.active.v1',
  history: 'outstep.history.v1',
  prefs: 'outstep.prefs.v1',
}

function read(key) {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function write(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

/* --- Active run ------------------------------------------------------------ */

export function loadActiveRun() {
  const run = read(KEYS.active)
  if (!run || run.version !== 1 || !run.mission || !run.tasks) return null
  return run
}

export function saveActiveRun(run) {
  return write(KEYS.active, run)
}

export function clearActiveRun() {
  return write(KEYS.active, null)
}

/* --- History --------------------------------------------------------------- */

export function loadHistory() {
  const history = read(KEYS.history)
  return Array.isArray(history) ? history : []
}

export function saveHistory(entries) {
  return write(KEYS.history, Array.isArray(entries) ? entries : [])
}

export function upsertHistoryEntry(entry) {
  const history = loadHistory()
  const index = history.findIndex((item) => item.id === entry.id)
  if (index >= 0) history[index] = entry
  else history.unshift(entry)
  saveHistory(history)
  return history
}

/* --- Setup preferences ----------------------------------------------------- */

export function loadPrefs() {
  const prefs = read(KEYS.prefs)
  return prefs && typeof prefs === 'object' ? prefs : null
}

export function savePrefs(prefs) {
  return write(KEYS.prefs, prefs)
}
