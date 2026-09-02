// Focused test for the pure helper in admin/institutions/create-helpers.ts
// (create-institution error classification). No external imports, so (like
// [id]/helpers.test.mjs) this just transpiles and runs it directly.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import vm from 'node:vm'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const helpersPath = path.join(import.meta.dirname, 'create-helpers.ts')
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

const { classifyCreateError } = mod.exports

test('403 maps to a permission message', () => {
  assert.equal(classifyCreateError(403), "You don't have permission to create institutions.")
})

test('409 with a string detail surfaces the backend message verbatim', () => {
  assert.equal(
    classifyCreateError(409, 'An institution with slug "acme" already exists'),
    'An institution with slug "acme" already exists',
  )
})

test('409 with a non-string detail falls back to a generic conflict message', () => {
  assert.equal(classifyCreateError(409, { error: 'x' }), 'That value conflicts with an existing institution.')
})

test('422 maps to a validation message', () => {
  assert.equal(classifyCreateError(422), 'Check the highlighted fields and try again.')
})

test('500 and unknown/undefined statuses map to a generic retry message', () => {
  assert.equal(classifyCreateError(500), 'Something went wrong. Please try again.')
  assert.equal(classifyCreateError(undefined), 'Something went wrong. Please try again.')
})
