// Focused test for the pure helpers in institution/invites/helpers.ts
// (list formatting, display-status derivation, create-form validation,
// 403/409/500 classification). No external imports in helpers.ts, so
// (like auth-redirect.test.mjs) this just transpiles and runs it directly.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import vm from 'node:vm'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const helpersPath = path.join(import.meta.dirname, 'helpers.ts')
const source = fs.readFileSync(helpersPath, 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  },
})

const mod = new Module(helpersPath)
mod.filename = helpersPath
mod.paths = Module._nodeModulePaths(path.dirname(helpersPath))
vm.runInThisContext(Module.wrap(outputText))(
  mod.exports, mod.require, mod, mod.filename, path.dirname(helpersPath)
)

const {
  classifyLoadError, deriveDisplayStatus, usesLabel, formatInviteDate,
  validateMaxUses, validateExpiration,
} = mod.exports

// ── classifyLoadError: 401/403 -> denied, 409 -> multiple, else -> error ──

test('403 classifies as denied', () => {
  assert.equal(classifyLoadError(403), 'denied')
})

test('401 classifies as denied', () => {
  assert.equal(classifyLoadError(401), 'denied')
})

test('409 classifies as multiple', () => {
  assert.equal(classifyLoadError(409), 'multiple')
})

test('500 and network errors (undefined status) classify as generic retryable error', () => {
  assert.equal(classifyLoadError(500), 'error')
  assert.equal(classifyLoadError(undefined), 'error')
})

test('429 classifies as generic error (no special-cased rate-limit UI on load)', () => {
  assert.equal(classifyLoadError(429), 'error')
})

// ── deriveDisplayStatus: display-only projection, never mutates backend status ──

test('revoked status stays revoked regardless of expiry', () => {
  assert.equal(deriveDisplayStatus('revoked', null), 'revoked')
  assert.equal(deriveDisplayStatus('revoked', '2099-01-01T00:00:00Z'), 'revoked')
})

test('active status with no expiry stays active', () => {
  assert.equal(deriveDisplayStatus('active', null), 'active')
})

test('active status with a future expiry stays active', () => {
  const now = new Date('2026-01-01T00:00:00Z')
  assert.equal(deriveDisplayStatus('active', '2026-06-01T00:00:00Z', now), 'active')
})

test('active status with a past expiry displays as expired (backend status column is untouched)', () => {
  const now = new Date('2026-06-01T00:00:00Z')
  assert.equal(deriveDisplayStatus('active', '2026-01-01T00:00:00Z', now), 'expired')
})

test('expiry exactly at now displays as expired', () => {
  const now = new Date('2026-06-01T00:00:00Z')
  assert.equal(deriveDisplayStatus('active', '2026-06-01T00:00:00Z', now), 'expired')
})

// ── usesLabel: bounded vs unlimited ──────────────────────────────────────

test('bounded invite shows used/remaining', () => {
  assert.equal(usesLabel(3, 7), '3 used · 7 remaining')
})

test('unlimited invite (remaining_uses null) shows Unlimited', () => {
  assert.equal(usesLabel(3, null), '3 used · Unlimited')
})

// ── formatInviteDate: short format, null -> No expiration ───────────────

test('a real date formats as short month/day/year', () => {
  assert.equal(formatInviteDate('2026-09-30T12:30:00.000Z'), 'Sep 30, 2026')
})

test('null date shows No expiration', () => {
  assert.equal(formatInviteDate(null), 'No expiration')
})

test('invalid date string falls back to No expiration', () => {
  assert.equal(formatInviteDate('not-a-date'), 'No expiration')
})

// ── validateMaxUses: blank -> unlimited, 1+ int -> valid, 0/negative/decimal -> invalid ──

test('blank max_uses is valid (unlimited)', () => {
  assert.deepEqual(validateMaxUses(''), { valid: true, value: null })
  assert.deepEqual(validateMaxUses('   '), { valid: true, value: null })
})

test('a positive integer is valid', () => {
  assert.deepEqual(validateMaxUses('10'), { valid: true, value: 10 })
})

test('zero is invalid', () => {
  const result = validateMaxUses('0')
  assert.equal(result.valid, false)
  assert.equal(result.error, 'Must be blank or a whole number of 1 or more.')
})

test('a negative number is invalid', () => {
  assert.equal(validateMaxUses('-1').valid, false)
})

test('a decimal is invalid', () => {
  assert.equal(validateMaxUses('1.5').valid, false)
})

// ── validateExpiration: blank -> no expiration, future -> valid, past/now -> invalid ──

test('blank expiration is valid (no expiration)', () => {
  assert.deepEqual(validateExpiration(''), { valid: true, iso: null })
})

test('a future datetime-local value is valid and converts to a UTC ISO string', () => {
  const now = new Date('2026-01-01T00:00:00Z')
  const result = validateExpiration('2099-06-15T18:00', now)
  assert.equal(result.valid, true)
  assert.equal(result.iso, new Date('2099-06-15T18:00').toISOString())
})

test('a past datetime-local value is invalid', () => {
  const now = new Date('2026-06-01T00:00:00Z')
  const result = validateExpiration('2020-01-01T00:00', now)
  assert.equal(result.valid, false)
})

test('a datetime-local value equal to now is invalid', () => {
  const now = new Date('2026-06-01T12:00:00Z')
  // Constructed so `new Date(raw)` parses to exactly `now` in this process's
  // own local timezone -- this is the same interpretation the page relies on.
  const raw = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}T${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const result = validateExpiration(raw, now)
  assert.equal(result.valid, false)
})

// ── timezone regression: never append "Z" to a datetime-local value ──────

test('validateExpiration does NOT treat the local input as UTC (no naive +Z parsing)', () => {
  // If the implementation regressed to `new Date(raw + 'Z')`, this would
  // parse as UTC instead of local time, and the resulting ISO string would
  // differ from the correct local-time interpretation whenever the host
  // timezone offset is non-zero.
  const raw = '2099-06-15T18:00'
  const correct = new Date(raw).toISOString()
  const wrong = new Date(raw + 'Z').toISOString()
  const result = validateExpiration(raw, new Date('2026-01-01T00:00:00Z'))
  assert.equal(result.iso, correct)
  // This assertion only has teeth on a host whose local offset isn't UTC+0;
  // guard so CI running in UTC doesn't get a false failure.
  if (correct !== wrong) {
    assert.notEqual(result.iso, wrong)
  }
})
