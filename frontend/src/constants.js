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

/**
 * Mission archetypes: the creative style each generation is built around.
 * The backend assigns one per generation; ids match `MissionArchetype`
 * in backend/schemas.py. Missions saved before this field existed have
 * no archetype - always render defensively.
 */
export const ARCHETYPES = [
  {
    id: 'visual_detective',
    label: 'Visual Detective',
    blurb: 'Hunt for visual clues other people walk past.',
  },
  {
    id: 'nature_bingo',
    label: 'Nature Bingo',
    blurb: 'Tick off a checklist of small natural finds.',
  },
  {
    id: 'urban_archaeologist',
    label: 'Urban Archaeologist',
    blurb: 'Read the layers of history in ordinary streets.',
  },
  {
    id: 'colour_quest',
    label: 'Colour Quest',
    blurb: 'Chase a palette through the neighbourhood.',
  },
  {
    id: 'pattern_breaker',
    label: 'Pattern Breaker',
    blurb: 'Find patterns, then find what breaks them.',
  },
  {
    id: 'sound_mapper',
    label: 'Sound Mapper',
    blurb: 'Map the soundscape you usually filter out.',
  },
  {
    id: 'route_quest',
    label: 'Route Quest',
    blurb: 'A route with self-made rules.',
  },
  {
    id: 'micro_explorer',
    label: 'Micro-Explorer',
    blurb: "A whole world at fingertips' range.",
  },
  {
    id: 'movement_quest',
    label: 'Movement Quest',
    blurb: 'The body is the way through the mission.',
  },
]

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
