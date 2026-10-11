/**
 * Pure helpers for mission payloads coming from the API.
 *
 * Missions saved in history before the archetype/objective update lack the
 * newer fields; every helper here degrades gracefully so old entries keep
 * rendering (and tests can pin that behaviour down).
 */

import { ARCHETYPES } from '../constants.js'

/** Human label for an archetype id; '' when unknown or missing. */
export function archetypeLabel(id) {
  return ARCHETYPES.find((a) => a.id === id)?.label ?? ''
}

/** One-line description of an archetype's flavour; '' when unknown. */
export function archetypeBlurb(id) {
  return ARCHETYPES.find((a) => a.id === id)?.blurb ?? ''
}

/** The mission's objective sentence, or '' for pre-update missions. */
export function missionObjective(mission) {
  return typeof mission?.objective === 'string' ? mission.objective.trim() : ''
}

/** Total planned minutes across the mission's tasks (0 when absent). */
export function taskMinutesTotal(tasks) {
  if (!Array.isArray(tasks)) return 0
  return tasks.reduce((sum, task) => sum + (Number(task?.target_minutes) || 0), 0)
}
