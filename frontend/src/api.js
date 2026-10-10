/**
 * API client. Talks to the FastAPI backend only — no keys ever reach here.
 * Errors carry `{ message, issues }` so the UI can show exactly what failed.
 */

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
  } catch {
    const error = new Error(
      'Could not reach the OutStep server. Is the backend running on port 8000?',
    )
    error.issues = []
    throw error
  }

  let body = null
  try {
    body = await response.json()
  } catch {
    /* non-JSON response handled below */
  }

  if (!response.ok) {
    const detail = body?.detail
    const error = new Error(
      (typeof detail === 'string' && detail) ||
        detail?.message ||
        `Request failed with status ${response.status}.`,
    )
    error.issues = Array.isArray(detail?.issues) ? detail.issues : []
    throw error
  }
  return body
}

export function fetchConfig() {
  return request('/api/config')
}

export function generateMission(prefs) {
  return request('/api/generate-mission', {
    method: 'POST',
    body: JSON.stringify(prefs),
  })
}

export function fetchSampleMission(prefs) {
  const query = new URLSearchParams({
    activity: prefs.activity,
    duration_minutes: String(prefs.durationMinutes),
    energy: prefs.energy,
    difficulty: prefs.difficulty,
  })
  return request(`/api/sample-mission?${query.toString()}`)
}
