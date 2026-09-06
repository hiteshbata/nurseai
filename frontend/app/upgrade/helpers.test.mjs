// Focused test for the pure helpers in app/upgrade/helpers.ts (plan card
// action/label decisions + institution upgrade-rail filtering). Same
// transpile-and-run approach as admin/institutions/[id]/helpers.test.mjs --
// helpers.ts only has an `import type` (erased at compile time), so the
// transpiled output has no external imports to resolve.
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
  getCardAction, getCardLabel, isCheckoutAllowed,
  INSTITUTION_MODULE_ROWS,
} = mod.exports

// ── getCardAction ─────────────────────────────────────────────────────

test('getCardAction: current plan is "current"', () => {
  assert.equal(getCardAction({ id: 'basic', is_current: true, is_purchasable: false }), 'current')
})

test('getCardAction: not current, not purchasable (e.g. Free) is "included"', () => {
  assert.equal(getCardAction({ id: 'free', is_current: false, is_purchasable: false }), 'included')
})

test('getCardAction: not current, purchasable is "upgrade"', () => {
  assert.equal(getCardAction({ id: 'pro', is_current: false, is_purchasable: true }), 'upgrade')
})

test('getCardAction: missing entitlement fails closed to "included", never "upgrade"', () => {
  assert.equal(getCardAction(undefined), 'included')
})

// ── getCardLabel ──────────────────────────────────────────────────────

test('getCardLabel maps each action to its label', () => {
  assert.equal(getCardLabel('current', 'Get Pro'), 'Current Plan')
  assert.equal(getCardLabel('included', 'Get Pro'), 'Included')
  assert.equal(getCardLabel('upgrade', 'Get Pro'), 'Get Pro')
})

// ── isCheckoutAllowed ────────────────────────────────────────────────

test('isCheckoutAllowed is true only for "upgrade"', () => {
  assert.equal(isCheckoutAllowed('upgrade'), true)
  assert.equal(isCheckoutAllowed('current'), false)
  assert.equal(isCheckoutAllowed('included'), false)
})

test('a current Free plan still resolves to a disabled, non-checkout card', () => {
  const freeEntitlement = { id: 'free', is_current: true, is_purchasable: false }
  const action = getCardAction(freeEntitlement)
  assert.equal(action, 'current')
  assert.equal(getCardLabel(action, 'Start Free'), 'Current Plan')
  assert.equal(isCheckoutAllowed(action), false)
})

// ── INSTITUTION_MODULE_ROWS ─────────────────────────────────────────

test('INSTITUTION_MODULE_ROWS covers all five effective_access module keys', () => {
  assert.deepEqual(
    INSTITUTION_MODULE_ROWS.map((r) => r.key),
    ['speaking', 'reading', 'listening', 'writing', 'mock']
  )
})
