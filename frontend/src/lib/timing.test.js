import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatClock,
  isOverTarget,
  isPastPlanned,
  missionElapsedMs,
  progressRatio,
  remainingMs,
  summarizeRun,
  taskElapsedMs,
} from './timing.js'

const MIN = 60_000
const START = 1_000_000

test('elapsed counts from timestamps', () => {
  assert.equal(missionElapsedMs(START + 5 * MIN, START), 5 * MIN)
})

test('elapsed is never negative', () => {
  assert.equal(missionElapsedMs(START - 1000, START), 0)
  assert.equal(missionElapsedMs(START, null), 0)
})

test('active pause is excluded', () => {
  const now = START + 10 * MIN
  assert.equal(missionElapsedMs(now, START, START + 6 * MIN), 6 * MIN)
})

test('completed pause time is excluded', () => {
  assert.equal(
    missionElapsedMs(START + 20 * MIN, START, null, 5 * MIN),
    15 * MIN,
  )
})

test('task clock uses its own pause fields', () => {
  const taskStart = START + 10 * MIN
  const now = taskStart + 7 * MIN
  assert.equal(taskElapsedMs(now, taskStart, now - 3 * MIN), 4 * MIN)
  assert.equal(taskElapsedMs(now + 2 * MIN, taskStart, null, 3 * MIN), 6 * MIN)
})

test('pause before a task starts does not leak in', () => {
  const taskStart = START + 10 * MIN
  assert.equal(taskElapsedMs(taskStart + 5 * MIN, taskStart), 5 * MIN)
})

test('remaining and past-planned', () => {
  assert.equal(remainingMs(0, 30), 30 * MIN)
  assert.equal(remainingMs(45 * MIN, 30), 0)
  assert.equal(isPastPlanned(30 * MIN, 30), false)
  assert.equal(isPastPlanned(30 * MIN + 1, 30), true)
})

test('over target', () => {
  assert.equal(isOverTarget(5 * MIN, 5), false)
  assert.equal(isOverTarget(5 * MIN + 1, 5), true)
})

test('progress clamped', () => {
  assert.equal(progressRatio(15 * MIN, 30), 0.5)
  assert.equal(progressRatio(60 * MIN, 30), 1)
  assert.equal(progressRatio(0, 0), 1)
})

test('clock formatting', () => {
  assert.equal(formatClock(0), '0:00')
  assert.equal(formatClock(9 * MIN + 5_000), '9:05')
  assert.equal(formatClock(65 * MIN), '1:05:00')
  assert.equal(formatClock(-500), '0:00')
})

test('summary counts and never fails the user', () => {
  const stats = summarizeRun(
    ['completed', 'skipped', 'completed', 'pending'],
    32 * MIN,
    30,
  )
  assert.equal(stats.completed, 2)
  assert.equal(stats.skipped, 1)
  assert.equal(stats.pending, 1)
  assert.equal(stats.past_planned, true)
  assert.equal('failed' in stats, false)
  assert.equal(JSON.stringify(stats).includes('fail'), false)
})
