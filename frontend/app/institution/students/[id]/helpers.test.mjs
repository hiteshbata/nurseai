// Focused test for the pure helpers in institution/students/[id]/helpers.ts.
// No external imports in helpers.ts, so (like ../page.test.mjs) this just
// transpiles and runs it directly.
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

const { classifyLoadError, moduleLabel, formatDateTime, lastActivityLabel } = mod.exports

// ── classifyLoadError: 403 denied / 409 multiple / 404 notFound / other ──

test('403 classifies as denied', () => {
  assert.equal(classifyLoadError(403), 'denied')
})

test('401 classifies as denied', () => {
  assert.equal(classifyLoadError(401), 'denied')
})

test('409 classifies as multiple', () => {
  assert.equal(classifyLoadError(409), 'multiple')
})

test('404 classifies as notFound (cross-institution or nonexistent student)', () => {
  assert.equal(classifyLoadError(404), 'notFound')
})

test('500 and network errors (undefined status) classify as generic retryable error', () => {
  assert.equal(classifyLoadError(500), 'error')
  assert.equal(classifyLoadError(undefined), 'error')
})

// ── moduleLabel ──────────────────────────────────────────────────────────

test('known modules map to display labels', () => {
  assert.equal(moduleLabel('speaking'), 'Speaking')
  assert.equal(moduleLabel('mock_test'), 'Mock Test')
})

test('unknown module falls back to the raw value', () => {
  assert.equal(moduleLabel('something_new'), 'something_new')
})

// ── formatDateTime / lastActivityLabel ──────────────────────────────────

test('null/invalid dates fall back to an em dash', () => {
  assert.equal(formatDateTime(null), '—')
  assert.equal(formatDateTime('not-a-date'), '—')
})

test('a valid ISO date formats without throwing', () => {
  assert.notEqual(formatDateTime('2026-08-20T10:00:00Z'), '—')
})

test('null last_seen_at shows "No activity recorded"', () => {
  assert.equal(lastActivityLabel(null), 'No activity recorded')
})

test('a real last_seen_at formats as a date/time, not the placeholder', () => {
  assert.notEqual(lastActivityLabel('2026-08-20T10:00:00Z'), 'No activity recorded')
})
