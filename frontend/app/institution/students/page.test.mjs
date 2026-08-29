// Focused test for the pure helpers in institution/students/helpers.ts
// (roster formatting + 403/409/500 classification). No external imports in
// helpers.ts, so (like auth-redirect.test.mjs) this just transpiles and
// runs it directly.
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

const { classifyLoadError, formatJoined, scoreLabel, sessionsLabel, mobileSessionsLabel } = mod.exports

// ── classifyLoadError: 403 access-restricted / 409 multi-institution / other ──

test('403 classifies as denied (item 15: Access restricted)', () => {
  assert.equal(classifyLoadError(403), 'denied')
})

test('401 classifies as denied', () => {
  assert.equal(classifyLoadError(401), 'denied')
})

test('409 classifies as multiple (item 15: safe multi-institution message)', () => {
  assert.equal(classifyLoadError(409), 'multiple')
})

test('500 and network errors (undefined status) classify as generic retryable error', () => {
  assert.equal(classifyLoadError(500), 'error')
  assert.equal(classifyLoadError(undefined), 'error')
})

// ── scoreLabel: missing-score em dash (item 20) ─────────────────────────

test('null latest_speaking_score renders as em dash', () => {
  assert.equal(scoreLabel(null), '—')
})

test('a real score renders as its number', () => {
  assert.equal(scoreLabel(390), '390')
})

// ── sessionsLabel / mobileSessionsLabel: unlimited + disabled-speaking (item 20) ──

test('desktop: normal quota shows "used / remaining"', () => {
  assert.equal(sessionsLabel(12, 8), '12 / 8 remaining')
})

test('desktop: null remaining (unlimited quota or speaking disabled) omits a false "0 remaining"', () => {
  assert.equal(sessionsLabel(12, null), '12 used')
})

test('mobile: normal quota shows "used · left"', () => {
  assert.equal(mobileSessionsLabel(12, 8), '12 used · 8 left')
})

test('mobile: null remaining shows an em dash instead of a false number', () => {
  assert.equal(mobileSessionsLabel(12, null), '12 used · — left')
})

// ── formatJoined ─────────────────────────────────────────────────────────

test('joined_at formats as short month + day', () => {
  assert.equal(formatJoined('2026-08-20T10:00:00Z'), 'Aug 20')
})

test('missing/invalid joined_at falls back to an em dash', () => {
  assert.equal(formatJoined(null), '—')
  assert.equal(formatJoined('not-a-date'), '—')
})
