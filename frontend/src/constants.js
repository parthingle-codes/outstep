export const ACTIVITIES = [
  {
    id: 'explore_nature',
    label: 'Explore Nature',
    blurb: 'Wander somewhere green and notice what you usually miss.',
  },
  {
    id: 'move',
    label: 'Move',
    blurb: 'Get your body going outside, at your own pace.',
  },
  {
    id: 'clear_my_head',
    label: 'Clear My Head',
    blurb: 'Shake off screen fog with a few gentle focusing tasks.',
  },
  {
    id: 'observe',
    label: 'Observe',
    blurb: 'Slow down and watch the world do its thing.',
  },
]

export const DURATIONS = [15, 30, 60]

export const ENERGY_LEVELS = [
  { id: 'low', label: 'Low', blurb: 'Easy does it' },
  { id: 'moderate', label: 'Moderate', blurb: 'A comfortable push' },
  { id: 'high', label: 'High', blurb: 'I want to sweat' },
]

export const DIFFICULTIES = [
  { id: 'chill', label: 'Chill', blurb: 'Low stakes, high vibe' },
  { id: 'steady', label: 'Steady', blurb: 'A gentle challenge' },
  { id: 'push', label: 'Push', blurb: 'Stretch me a little' },
]

export const DEFAULT_PREFS = {
  activity: 'explore_nature',
  durationMinutes: 30,
  energy: 'moderate',
  difficulty: 'steady',
  context: '',
}

export function activityLabel(id) {
  return ACTIVITIES.find((a) => a.id === id)?.label ?? id
}
