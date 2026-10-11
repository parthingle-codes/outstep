import test from 'node:test'
import assert from 'node:assert/strict'

import { ARCHETYPES } from '../constants.js'
import {
  archetypeBlurb,
  archetypeLabel,
  missionObjective,
  taskMinutesTotal,
} from './mission.js'

test('archetype labels and blurbs resolve for every known id', () => {
  assert.equal(ARCHETYPES.length, 9)
  for (const archetype of ARCHETYPES) {
    assert.equal(archetypeLabel(archetype.id), archetype.label)
    assert.ok(archetypeBlurb(archetype.id).length > 0)
  }
})

test('unknown or missing archetypes fall back to an empty label', () => {
  assert.equal(archetypeLabel('banana'), '')
  assert.equal(archetypeLabel(undefined), '')
  assert.equal(archetypeLabel(null), '')
  assert.equal(archetypeBlurb(undefined), '')
})

test('missionObjective returns the objective, trimmed', () => {
  const mission = { objective: '  Count three red doors on your street.  ' }
  assert.equal(missionObjective(mission), 'Count three red doors on your street.')
})

test('missions saved before the objective field keep rendering', () => {
  // History entries from older versions have no objective or archetype.
  assert.equal(missionObjective({ title: 'Old mission' }), '')
  assert.equal(missionObjective({}), '')
  assert.equal(missionObjective(null), '')
  assert.equal(archetypeLabel(undefined), '')
})

test('taskMinutesTotal sums task targets', () => {
  const tasks = [{ target_minutes: 8 }, { target_minutes: 6 }, { target_minutes: 10 }]
  assert.equal(taskMinutesTotal(tasks), 24)
  assert.equal(taskMinutesTotal([]), 0)
  assert.equal(taskMinutesTotal(undefined), 0)
  assert.equal(taskMinutesTotal(null), 0)
  // Defensive against malformed entries.
  assert.equal(taskMinutesTotal([{ target_minutes: 'x' }, { target_minutes: 5 }]), 5)
})
