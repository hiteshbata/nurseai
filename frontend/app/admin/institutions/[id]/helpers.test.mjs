// Focused test for the pure helpers in admin/institutions/[id]/helpers.ts
// (Settings-form field validation, quota validation, save-error
// classification). No external imports in helpers.ts, so (like
// institution/invites/page.test.mjs) this just transpiles and runs it
// directly.
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
  MODULE_VALUES, validateRequired, validateContactEmail, validateQuota, classifySaveError,
} = mod.exports

// ── MODULE_VALUES: mirrors the backend CHECK constraint ─────────────────

test('MODULE_VALUES lists exactly the five known modules', () => {
  assert.deepEqual(MODULE_VALUES, ['speaking', 'reading', 'listening', 'writing', 'mock_tests'])
})

// ── validateRequired ──────────────────────────────────────────────────

test('blank/whitespace-only value is invalid', () => {
  assert.equal(validateRequired('', 'Name').valid, false)
  assert.equal(validateRequired('   ', 'Name').valid, false)
  assert.equal(validateRequired('  ', 'Name').error, 'Name is required.')
})

test('a non-blank value is valid', () => {
  assert.equal(validateRequired('Acme', 'Name').valid, true)
})

// ── validateContactEmail ──────────────────────────────────────────────

test('a well-formed email is valid', () => {
  assert.equal(validateContactEmail('admin@example.com').valid, true)
})

test('a malformed email is invalid', () => {
  const result = validateContactEmail('not-an-email')
  assert.equal(result.valid, false)
  assert.equal(result.error, 'Enter a valid email address.')
})

test('a blank email is invalid', () => {
  assert.equal(validateContactEmail('').valid, false)
})

// ── validateQuota: unlike invites' max_uses, blank is NOT unlimited here ──

test('a positive integer is valid', () => {
  assert.deepEqual(validateQuota('20'), { valid: true, value: 20 })
})

test('blank is invalid (Settings always submits a concrete quota)', () => {
  assert.equal(validateQuota('').valid, false)
})

test('zero is invalid', () => {
  assert.equal(validateQuota('0').valid, false)
})

test('a negative number is invalid', () => {
  assert.equal(validateQuota('-5').valid, false)
})

test('a decimal is invalid', () => {
  assert.equal(validateQuota('1.5').valid, false)
})

// ── classifySaveError ───────────────────────────────────────────────────

test('403 maps to a permission message', () => {
  assert.equal(classifySaveError(403), "You don't have permission to modify this institution.")
})

test('404 maps to a not-found message', () => {
  assert.equal(classifySaveError(404), 'Institution not found.')
})

test('409 with a string detail surfaces the backend message verbatim', () => {
  assert.equal(
    classifySaveError(409, 'An institution with slug "acme" already exists'),
    'An institution with slug "acme" already exists',
  )
})

test('409 with a non-string detail falls back to a generic conflict message', () => {
  assert.equal(classifySaveError(409, { error: 'x' }), 'That value conflicts with an existing institution.')
})

test('422 maps to a validation message', () => {
  assert.equal(classifySaveError(422), 'Check the highlighted fields and try again.')
})

test('500 and unknown/undefined statuses map to a generic retry message', () => {
  assert.equal(classifySaveError(500), 'Something went wrong. Please try again.')
  assert.equal(classifySaveError(undefined), 'Something went wrong. Please try again.')
})
